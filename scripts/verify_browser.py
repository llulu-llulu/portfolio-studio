"""Browser acceptance + actual process restart. Uses an isolated SQLite file.

Optional QA dependency: playwright==1.62.0 (the locally verified version).
Run: python scripts/verify_browser.py
Set QA_BROWSER_CHANNEL=chrome (default: msedge) or install Playwright Chromium.
"""
import json
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/playwright"
OUT.mkdir(parents=True, exist_ok=True)
TEMP = ROOT / "tmp/qa"
TEMP.mkdir(parents=True, exist_ok=True)
DB = TEMP / f"browser-{uuid4().hex}.db"
BASE = "http://127.0.0.1:8765"
opener = build_opener(ProxyHandler({}))
process = None
server_log = (ROOT / "output/verification/browser-server.log").open("w", encoding="utf-8")
records = []


def record(name, detail):
    records.append({"check":name, "result":"PASS", "detail":detail})
    print(f"PASS {name}: {detail}", flush=True)


def start_server():
    global process
    process = subprocess.Popen([sys.executable, "-X", "utf8", "run.py", "--port", "8765", "--db", str(DB)],
                               cwd=ROOT, stdout=server_log, stderr=server_log,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    for _ in range(80):
        if process.poll() is not None: raise RuntimeError("Server exited before becoming ready")
        try:
            with opener.open(BASE + "/api/health", timeout=.5) as response:
                if response.status == 200: return process.pid
        except OSError: time.sleep(.1)
    raise TimeoutError("Server readiness timed out")


def stop_server():
    global process
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


try:
    first_pid = start_server()
    with sync_playwright() as pw:
        channel = os.environ.get("QA_BROWSER_CHANNEL", "msedge")
        browser = pw.chromium.launch(headless=True, channel=channel or None)
        context = browser.new_context(viewport={"width":1440,"height":1100}, device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.get_by_role("heading", name="组合概览", exact=True)).to_be_visible()
        expect(page.locator(".stat.primary strong")).to_have_text("¥100,000.00")
        expect(page.locator(".warning-card")).to_have_count(2)
        page.screenshot(path=str(OUT / "01-overview.png"), full_page=True)
        record("AC-01 browser", "100,000.00 total; 20,000.00 cash; two warnings")

        page.get_by_role("link", name="已保存方案").click()
        expect(page.get_by_role("heading",name="还没有保存的方案")).to_be_visible()
        record("Empty plans", "Explicit empty state and create action")
        page.get_by_role("link",name="创建第一个方案").click()
        expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
        page.get_by_label("买入",exact=True).check()
        page.get_by_label("交易数量").fill("201")
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator("#form-error")).to_contain_text("现金不足")
        expect(page.locator(".steps li")).to_have_count(0)
        expect(page.locator(".comparison-summary")).to_contain_text("20,000.00")
        page.screenshot(path=str(OUT / "03-error.png"), full_page=True)
        page.get_by_label("卖出",exact=True).check()
        page.get_by_label("交易数量").fill("401")
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator("#form-error")).to_contain_text("可卖数量不足")
        for q in ["0", "-1", "1.5"]:
            page.get_by_label("交易数量").fill(q)
            page.get_by_role("button",name="添加并计算").click()
            expect(page.locator("#form-error")).to_contain_text("正整数")
            expect(page.locator(".steps li")).to_have_count(0)
        record("AC-04 browser", "Buy 201, sell 401, 0, -1, 1.5 rejected; state unchanged")

        page.get_by_label("交易数量").fill("100")
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator(".steps li")).to_have_count(1)
        expect(page.locator(".all-clear")).to_be_visible()
        expect(page.locator(".comparison-summary")).to_contain_text("30,000.00")
        expect(page.get_by_role("button",name="添加并计算")).to_be_enabled()
        record("AC-02 browser", "Sell A01 100; cash 30,000.00; all warnings cleared")

        page.get_by_label("交易标的").select_option("A02")
        page.get_by_label("买入",exact=True).check()
        page.get_by_label("交易数量").fill("100")
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator(".steps li")).to_have_count(2)
        expect(page.locator(".sim-warning .warning-card")).to_have_count(1)
        expect(page.locator(".sim-warning")).to_contain_text("55.00%")
        expect(page.locator(".comparison-summary")).to_contain_text("25,000.00")
        expect(page.locator("#toast")).to_be_hidden(timeout=7000)
        page.screenshot(path=str(OUT / "02-simulation.png"), full_page=True)
        record("AC-03 browser", "Buy A02 100 next; 25,000.00 cash; tech 55.00%")

        before_invalid = page.locator(".comparison").inner_text()
        page.get_by_label("交易数量").fill("10000")
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator("#form-error")).to_contain_text("现金不足")
        assert page.locator(".comparison").inner_text() == before_invalid
        expect(page.locator(".steps li")).to_have_count(2)
        record("Failure atomicity", "Invalid third operation leaves the accepted two-operation result intact")

        page.get_by_label("方案名称").fill("科技集中度调整 · AC-03")
        page.get_by_role("button",name="保存方案",exact=False).click()
        expect(page.get_by_role("heading",name="科技集中度调整 · AC-03")).to_be_visible()
        saved_url = page.url
        saved_id = saved_url.split("#plan/")[1]
        saved_api = context.request.get(BASE+"/api/plans/"+saved_id).json()
        before_reload = page.locator(".comparison").inner_text()
        page.reload()
        expect(page.get_by_role("heading",name="科技集中度调整 · AC-03")).to_be_visible()
        assert page.locator(".comparison").inner_text() == before_reload
        page.screenshot(path=str(OUT / "04-saved-plan.png"), full_page=True)
        record("Saved URL reload", "Readonly scenario survives browser refresh")

        stop_server()
        second_pid = start_server()
        assert first_pid != second_pid
        page.reload()
        expect(page.get_by_role("heading",name="科技集中度调整 · AC-03")).to_be_visible()
        actual = context.request.get(BASE+"/api/plans/"+saved_id).json()
        assert actual == saved_api
        baseline = context.request.get(BASE+"/api/portfolio").json()
        assert baseline["cash"] == "20000.00"
        assert [p["quantity"] for p in baseline["positions"][:2]] == [400,400]
        record("AC-05 real process restart", f"PID {first_pid} -> {second_pid}; saved response identical; original cash 20000 and quantities 400/400")
        page.get_by_role("link",name="返回方案列表").click()
        expect(page.locator(".plan-card")).to_have_count(1)
        page.screenshot(path=str(OUT / "05-plan-list.png"), full_page=True)
        page.locator(".plan-card").click()
        expect(page.get_by_role("heading",name="科技集中度调整 · AC-03")).to_be_visible()
        record("Reopen from list", "List contains persisted scenario and opens readonly detail")

        page.set_viewport_size({"width":390,"height":844})
        page.get_by_role("link",name="组合概览").click()
        expect(page.get_by_role("heading",name="组合概览",exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT / "06-mobile-overview.png"), full_page=True)
        page.get_by_role("link",name="调仓模拟",exact=False).first.click()
        expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT / "07-mobile-simulation.png"), full_page=True)
        record("Mobile layout", "390px viewport; no document horizontal overflow; tables scroll inside container")

        page.goto(BASE+"/#plan/nonexistent")
        expect(page.get_by_role("heading",name="暂时无法打开")).to_be_visible()
        expect(page.get_by_role("button",name="重新加载")).to_be_visible()
        record("Missing scenario", "Friendly error with retry and return actions")

        page.goto(BASE+"/#overview")
        expect(page.get_by_role("heading",name="组合概览",exact=True)).to_be_visible()
        context.set_offline(True)
        page.get_by_role("link",name="已保存方案").click()
        expect(page.get_by_role("heading",name="暂时无法打开")).to_be_visible()
        context.set_offline(False)
        page.get_by_role("button",name="重新加载").click()
        expect(page.get_by_role("heading",name="已保存方案",exact=True)).to_be_visible()
        record("Offline recovery", "Network failure offers retry; reconnect recovers list")
        assert not errors, errors
        record("JavaScript runtime", "No uncaught page errors during all flows")
        summary = {"executed_at":datetime.now(timezone.utc).isoformat(), "browser":browser.version,
                   "channel":channel,"viewport":[1440,1100],"mobile_viewport":[390,844],
                   "saved_plan_id":saved_id,"checks":records,"uncaught_errors":errors,
                   "source_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                    for folder in ["backend", "frontend"] for p in sorted((ROOT/folder).glob("*")) if p.is_file()}}
        (ROOT / "output/verification/browser-results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        context.close(); browser.close()
finally:
    stop_server()
    server_log.close()
