"""Atomic SQLite saves, immutable source snapshots, and idempotent save requests."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.domain import BusinessError, ENGINE_VERSION, simulate


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PlanStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, created_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, operations_json TEXT NOT NULL,
                engine_version TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, name, request_id, snapshot, operations):
        snapshot_json, operations_json = encode(snapshot), encode(operations)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM plans WHERE request_id = ?", (request_id,)).fetchone()
            if existing:
                if (existing["name"], existing["snapshot_json"], existing["operations_json"]) != (name, snapshot_json, operations_json):
                    raise BusinessError("SAVE_CONFLICT", "此保存请求已用于另一个方案，请重新发起保存", status=409)
                return existing["id"], False
            plan_id = str(uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            db.execute("INSERT INTO plans VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (plan_id, request_id, name, created_at, snapshot_json, operations_json, ENGINE_VERSION))
            return plan_id, True

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT id, name, created_at, snapshot_json, operations_json FROM plans ORDER BY created_at DESC, id DESC").fetchall()
        return [{"id": row["id"], "name": row["name"], "created_at": row["created_at"],
                 "snapshot_id": json.loads(row["snapshot_json"])["snapshot_id"],
                 "operation_count": len(json.loads(row["operations_json"]))} for row in rows]

    def get(self, plan_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            raise BusinessError("PLAN_NOT_FOUND", "该方案不存在，请返回方案列表", status=404)
        if row["engine_version"] != ENGINE_VERSION:
            raise BusinessError("ENGINE_VERSION_MISMATCH", "此方案需要旧版计算引擎，当前版本无法重放", status=409)
        snapshot, operations = json.loads(row["snapshot_json"]), json.loads(row["operations_json"])
        return {"id": row["id"], "name": row["name"], "created_at": row["created_at"],
                "operations": operations, "result": simulate(snapshot, operations)}
