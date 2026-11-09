import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import create_app
from tests.test_domain import seed, trade


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "plans.db"
        self.client = TestClient(create_app(self.db))
        self.operations = [trade(), trade("A02", "buy", 100)]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def body(self, **changes):
        return {"snapshot_id":"SNAP-20261102", "operations": self.operations,
                "name":"集中度调整", "request_id":str(uuid4()), **changes}

    def test_read_portfolio_and_simulation(self):
        self.assertEqual(self.client.get("/api/portfolio").json()["total_assets"], "100000.00")
        r = self.client.post("/api/simulations", json={"snapshot_id":"SNAP-20261102", "operations":self.operations})
        self.assertEqual((r.status_code, r.json()["after"]["cash"]), (200, "25000.00"))

    def test_AC05_save_reopen_new_application_and_original_isolation(self):
        before = self.client.get("/api/portfolio").json()
        saved = self.client.post("/api/plans", json=self.body())
        self.assertEqual(saved.status_code, 201)
        new_client = TestClient(create_app(self.db))
        try:
            reopened = new_client.get("/api/plans/" + saved.json()["id"])
            self.assertEqual(reopened.json(), saved.json())
            self.assertEqual(new_client.get("/api/portfolio").json(), before)
            self.assertEqual(len(new_client.get("/api/plans").json()["plans"]), 1)
        finally: new_client.close()

    def test_history_uses_saved_snapshot_after_seed_changes(self):
        saved = self.client.post("/api/plans", json=self.body()).json()
        data = seed(); data["instruments"][0]["price"] = "123.45"; data["snapshot_id"] = "NEW-SNAPSHOT"
        path = Path(self.temp.name) / "new.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        client = TestClient(create_app(self.db, path))
        try:
            self.assertEqual(client.get("/api/plans/" + saved["id"]).json(), saved)
            self.assertEqual(client.get("/api/portfolio").json()["snapshot_id"], "NEW-SNAPSHOT")
        finally: client.close()

    def test_invalid_plan_not_persisted(self):
        r = self.client.post("/api/plans", json=self.body(operations=[trade(quantity=401)]))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "INSUFFICIENT_HOLDINGS")
        self.assertEqual(self.client.get("/api/plans").json(), {"plans":[]})

    def test_idempotent_save_and_conflicting_retry(self):
        body = self.body()
        first = self.client.post("/api/plans", json=body)
        repeat = self.client.post("/api/plans", json=body)
        self.assertEqual((first.status_code, repeat.status_code), (201,200))
        self.assertEqual(first.json(), repeat.json())
        body["name"] = "different"
        self.assertEqual(self.client.post("/api/plans", json=body).status_code, 409)
        self.assertEqual(len(self.client.get("/api/plans").json()["plans"]), 1)

    def test_same_name_different_ids_are_allowed(self):
        first = self.client.post("/api/plans", json=self.body()).json()
        second = self.client.post("/api/plans", json=self.body()).json()
        self.assertNotEqual(first["id"], second["id"])

    def test_name_validation_and_empty_plan(self):
        for changes in [{"name":" "}, {"name":"x"*61}, {"operations":[]}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post("/api/plans", json=self.body(**changes)).status_code, 422)

    def test_stale_snapshot(self):
        self.assertEqual(self.client.post("/api/plans", json=self.body(snapshot_id="OLD")).status_code, 409)

    def test_malformed_json_unknown_fields_and_forged_result(self):
        r = self.client.post("/api/simulations", content="{broken", headers={"Content-Type":"application/json"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(self.client.post("/api/plans", json=self.body(after={"cash":"999"})).status_code, 422)

    def test_api_rejects_invalid_quantities(self):
        for q in [0, -1, 0.5, True, "100"]:
            with self.subTest(q=q):
                r = self.client.post("/api/simulations", json={"snapshot_id":"SNAP-20261102","operations":[trade(quantity=q)]})
                self.assertEqual(r.status_code, 422)
                self.assertEqual(r.json()["error"]["code"], "INVALID_QUANTITY")

    def test_missing_plan(self):
        r = self.client.get("/api/plans/nonexistent")
        self.assertEqual((r.status_code,r.json()["error"]["code"]), (404,"PLAN_NOT_FOUND"))

    def test_unavailable_storage_returns_retryable_error(self):
        with self.assertLogs(level="ERROR"), patch("backend.storage.PlanStore.list", side_effect=sqlite3.OperationalError("locked")):
            r = self.client.get("/api/plans")
        self.assertEqual((r.status_code,r.json()["error"]["code"]), (503,"STORAGE_UNAVAILABLE"))

    def test_engine_version_mismatch_is_explicit(self):
        plan = self.client.post("/api/plans", json=self.body()).json()
        db = sqlite3.connect(self.db)
        try:
            with db: db.execute("UPDATE plans SET engine_version='future'")
        finally: db.close()
        r = self.client.get("/api/plans/" + plan["id"])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"]["code"], "ENGINE_VERSION_MISMATCH")

    def test_static_serving_does_not_expose_local_data(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        for path in ["/data/plans.db", "/attachments/sample-data.json", "/static/../data/plans.db", "/static/%2e%2e/attachments/sample-data.json"]:
            with self.subTest(path=path): self.assertEqual(self.client.get(path).status_code,404)

    def test_openapi_documents_operation_fields(self):
        schemas = self.client.get("/openapi.json").json()["components"]["schemas"]
        operation = schemas["OperationInput"]
        self.assertEqual(set(operation["required"]), {"symbol", "side", "quantity"})
        self.assertEqual(operation["properties"]["side"]["enum"], ["buy", "sell"])
        self.assertEqual(operation["properties"]["quantity"]["minimum"], 1)
        self.assertFalse(operation["additionalProperties"])
        self.assertEqual(schemas["SimulationInput"]["properties"]["operations"]["items"]["$ref"], "#/components/schemas/OperationInput")

    def test_validation_error_identifies_operation_and_field(self):
        r = self.client.post("/api/simulations", json={"snapshot_id":"SNAP-20261102", "operations":[trade(),trade(quantity=1.5)]})
        self.assertEqual(r.status_code, 422)
        error = r.json()["error"]
        self.assertEqual((error["code"],error["field"],error["operation_index"]), ("INVALID_QUANTITY","quantity",2))
        self.assertIn("第 2 笔",error["message"])

    def test_unexpected_failure_returns_sanitized_json(self):
        client = TestClient(create_app(self.db), raise_server_exceptions=False)
        try:
            with self.assertLogs(level="ERROR"), patch("backend.storage.PlanStore.list", side_effect=RuntimeError("private filesystem details")):
                r = client.get("/api/plans")
            self.assertEqual(r.status_code, 500)
            self.assertEqual(r.json()["error"]["code"], "INTERNAL_ERROR")
            self.assertNotIn("private filesystem", r.text)
        finally: client.close()

    def test_duplicate_concurrent_save_creates_one_plan(self):
        from concurrent.futures import ThreadPoolExecutor
        body = self.body()
        def save_once(_):
            client = TestClient(create_app(self.db))
            try: return client.post("/api/plans", json=body)
            finally: client.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(save_once, range(4)))
        self.assertEqual(sorted(r.status_code for r in responses), [200,200,200,201])
        self.assertEqual(len({r.json()["id"] for r in responses}),1)
        self.assertEqual(len(self.client.get("/api/plans").json()["plans"]),1)
