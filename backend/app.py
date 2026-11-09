import json
import logging
import os
import sqlite3
from pathlib import Path
from uuid import UUID
from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from backend.domain import BusinessError, ENGINE_VERSION, MAX_OPERATIONS, evaluate, simulate, validate_snapshot
from backend.storage import PlanStore

ROOT = Path(__file__).resolve().parent.parent


class OperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: StrictStr = Field(description="快照中的标的代码，例如 A01")
    side: Literal["buy", "sell"]
    quantity: StrictInt = Field(ge=1, le=1_000_000_000, description="正整数股数，不接受小数、布尔值或字符串")


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: StrictStr
    operations: list[OperationInput] = Field(max_length=MAX_OPERATIONS)

    def trade_dicts(self):
        return [operation.model_dump() for operation in self.operations]


class SaveInput(SimulationInput):
    name: StrictStr = Field(min_length=1, max_length=60)
    request_id: UUID


class LocalHeadersMiddleware:
    """ASGI middleware without per-request streaming queues."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def with_headers(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store")]
            await send(message)
        await self.app(scope, receive, with_headers)


def create_app(db_path=None, seed_path=None):
    snapshot = json.loads(Path(seed_path or ROOT / "attachments/sample-data.json").read_text(encoding="utf-8"))
    validate_snapshot(snapshot)
    store = PlanStore(db_path or os.environ.get("PORTFOLIO_DB", str(ROOT / "data/plans.db")))
    app = FastAPI(title="投资组合分析与调仓模拟", version="1.0.0")
    app.add_middleware(LocalHeadersMiddleware)

    @app.exception_handler(BusinessError)
    async def business_error(request, error):
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        issue = error.errors()[0]
        location = issue["loc"][1:]
        field = ".".join(str(x) for x in location)
        code, message, index = "INVALID_REQUEST", "请求格式不正确，请检查必填字段", None
        if issue["type"] == "json_invalid":
            message = "请求内容不是有效的 JSON"
        elif location and location[0] == "operations":
            if len(location) > 1 and isinstance(location[1], int):
                index = location[1] + 1
                field = str(location[-1]) if len(location) > 2 else "operations"
                code, message = {
                    "quantity": ("INVALID_QUANTITY", "数量必须是 1 至 1,000,000,000 的正整数"),
                    "symbol": ("UNKNOWN_SYMBOL", "请提供有效的标的代码"),
                    "side": ("INVALID_SIDE", "交易方向只能是 buy 或 sell"),
                }.get(field, ("INVALID_OPERATION", "操作必须且只能包含 symbol、side、quantity"))
                message = f"第 {index} 笔：{message}"
            else:
                code, message = "INVALID_OPERATIONS", f"操作必须为列表，且最多 {MAX_OPERATIONS} 笔"
        elif location and location[0] == "name":
            code, message = "INVALID_NAME", "方案名称必须为 1–60 字"
        elif location and location[0] == "request_id":
            message = "保存请求标识无效，请重新发起保存"
        elif location and location[0] == "snapshot_id":
            message = "请提供有效的行情快照编号"
        elif issue["type"] == "extra_forbidden":
            message = f"请求包含不支持的字段：{field}"
        return JSONResponse(BusinessError(code, message, field=field, operation_index=index).payload(), status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, error):
        logging.exception("SQLite operation failed", exc_info=error)
        return JSONResponse(BusinessError("STORAGE_UNAVAILABLE", "本地保存暂时不可用，请稍后重试；当前模拟仍保留", status=503).payload(), status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        logging.exception("Unexpected application error", exc_info=error)
        return JSONResponse(BusinessError("INTERNAL_ERROR", "服务暂时无法完成请求，请稍后重试；当前模拟已保留", status=500).payload(), status_code=500)

    def check_snapshot(snapshot_id):
        if snapshot_id != snapshot["snapshot_id"]:
            raise BusinessError("SNAPSHOT_MISMATCH", "行情快照已变更，请刷新页面后重新模拟", status=409)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "engine_version": ENGINE_VERSION}

    @app.get("/api/portfolio")
    def portfolio():
        return evaluate(snapshot)

    @app.post("/api/simulations")
    def simulation(body: SimulationInput):
        check_snapshot(body.snapshot_id)
        return simulate(snapshot, body.trade_dicts())

    @app.get("/api/plans")
    def plans():
        return {"plans": store.list()}

    @app.post("/api/plans")
    def save(body: SaveInput):
        check_snapshot(body.snapshot_id)
        name = body.name.strip()
        if not name:
            raise BusinessError("INVALID_NAME", "请为方案填写非空名称", field="name")
        if not body.operations:
            raise BusinessError("EMPTY_PLAN", "请先添加至少一笔有效操作再保存")
        operations = body.trade_dicts()
        simulate(snapshot, operations)  # Never trust a browser's computed result.
        plan_id, created = store.save(name, str(body.request_id), snapshot, operations)
        return JSONResponse(store.get(plan_id), status_code=201 if created else 200)

    @app.get("/api/plans/{plan_id}")
    def plan(plan_id: str):
        return store.get(plan_id)

    @app.get("/")
    def index():
        return FileResponse(ROOT / "frontend/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
    return app
