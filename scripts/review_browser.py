"""Targeted review of state loss, request races, loading, and error recovery.

--probe records observations without stopping at pre-fix failures.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_support import ROOT, isolated_server

probe = "--probe" in sys.argv
source_root = Path(os.environ.get("QA_PROJECT_DIR", str(ROOT))).resolve()
checks = []


def check(name, expected, actual):
    passed = expected == actual
    checks.append({"check":name, "expected":expected, "actual":actual, "passed":passed})
    print(f"{'PASS' if passed else 'FAIL'} {name}: {actual!r}", flush=True)


def unload_blocked(page):
    return page.evaluate("""() => {
        const event = new Event('beforeunload', {cancelable:true});
        window.dispatchEvent(event);
        return event.defaultPrevented;
    }""")


with isolated_server() as url, sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, channel=os.environ.get("QA_BROWSER_CHANNEL", "msedge"))
    context = browser.new_context(viewport={"width":1440,"height":1100})
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/#simulate")
    expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
    page.get_by_role("button",name="添加并计算").click()
    expect(page.locator(".steps li")).to_have_count(1)
    check("Keyboard focus restored after calculation", "quantity", page.evaluate("document.activeElement.id"))
    page.get_by_role("link",name="组合概览").click()
    expect(page.get_by_role("heading",name="组合概览",exact=True)).to_be_visible()
    check("Unsaved draft protected on overview", True, unload_blocked(page))

    page.get_by_role("link",name="调仓模拟",exact=False).first.click()
    expect(page.locator(".steps li")).to_have_count(1)
    page.get_by_label("方案名称").fill("复审保存场景")
    pending = []
    page.route("**/api/plans", lambda route: pending.append(route))
    page.get_by_role("button",name="保存方案",exact=False).click()
    page.wait_for_timeout(150)  # Deliberately keep a save request pending while navigating.
    assert pending
    check("Save-specific loading label", True, "正在保存" in page.locator("#save-form button").inner_text())
    check("Duplicate submit disabled", True, page.locator("#save-form button").is_disabled())
    page.get_by_role("link",name="组合概览").click()
    expect(page.get_by_role("heading",name="组合概览",exact=True)).to_be_visible()
    retained_route = pending.pop()
    response = retained_route.fetch()
    saved = response.json()
    retained_route.fulfill(response=response)
    page.unroute("**/api/plans")
    expect(page.locator("#toast")).to_contain_text("方案已保存")
    page.wait_for_timeout(100)
    check("Late save does not hijack navigation", "#overview", page.evaluate("location.hash"))
    page.get_by_role("link",name="调仓模拟",exact=False).first.click()
    expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
    check("Saved draft does not warn on leaving", False, unload_blocked(page))

    page.route("**/api/plans", lambda route: route.fulfill(status=503, content_type="text/plain", body="Service Unavailable"))
    page.get_by_role("link",name="已保存方案").click()
    expect(page.get_by_role("heading",name="暂时无法打开")).to_be_visible()
    actual_error = page.locator('[role="alert"]').inner_text()
    check("Non-JSON server error is understandable", True, "服务暂时不可用" in actual_error)
    page.unroute("**/api/plans")
    page.get_by_role("button",name="重新加载").click()
    expect(page.locator(".plan-card")).to_have_count(1)
    check("Retry recovers saved list", True, "复审保存场景" in page.locator(".plan-card").inner_text())

    base_data = context.request.get(url + "/api/portfolio").json()
    base_data["rules"]["single_instrument_threshold"] = "0.25"
    base_data["rules"]["industry_threshold"] = "0.45"
    for warning in base_data["warnings"]:
        warning["threshold_pct"] = "45.00" if warning["type"] == "industry" else "25.00"
    page.route("**/api/portfolio", lambda route: route.fulfill(json=base_data))
    page.goto(url + "/#overview")
    page.reload()  # A hash-only navigation keeps the existing base; force a new API read.
    expect(page.get_by_role("heading",name="组合概览",exact=True)).to_be_visible()
    rules_text = page.locator(".rule-note").inner_text()
    check("Rule captions follow server snapshot", True, "25.00%" in rules_text and "45.00%" in rules_text)
    page.unroute("**/api/portfolio")

    if not probe:
        page.goto(url + "/#simulate")
        page.reload()
        expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
        page.get_by_role("button",name="添加并计算").click()
        expect(page.locator(".steps li")).to_have_count(1)
        page.get_by_label("方案名称").fill("保存失败重试")
        page.route("**/api/plans", lambda route: route.fulfill(status=503, json={"error":{"message":"本地保存暂时不可用，请稍后重试"}}))
        page.get_by_role("button",name="保存方案",exact=False).click()
        expect(page.locator("#save-error")).to_be_visible()
        check("Save error beside save form with draft retained", True,
              "本地保存暂时不可用" in page.locator(".save-panel").inner_text() and page.locator(".steps li").count()==1)
        page.unroute("**/api/plans")
        page.get_by_role("button",name="保存方案",exact=False).click()
        expect(page.get_by_role("heading",name="保存失败重试",exact=True)).to_be_visible()
        check("Save retry clears failure and persists plan", True, "已保存" in page.locator(".saved-banner").inner_text())

        malicious_name = '<img src=x onerror="window.bad=1">'
        malicious_plan = context.request.post(url+"/api/plans", data={
            "snapshot_id":"SNAP-20261102", "name":malicious_name,
            "request_id":__import__('uuid').uuid4().hex,
            "operations":[{"symbol":"A01","side":"sell","quantity":100}]}).json()
        page.goto(url+"/#plan/"+malicious_plan["id"])
        expect(page.get_by_role("heading",name=malicious_name,exact=True)).to_be_visible()
        check("Plan name displayed as text, not executed HTML", True,
              page.locator("#main img").count()==0 and page.evaluate("window.bad === undefined"))

        base_data["warnings"][0]["actual_pct"] = "25.00"
        page.route("**/api/portfolio", lambda route: route.fulfill(json=base_data))
        page.goto(url+"/#overview")
        page.reload()
        expect(page.locator(".rounding-note")).to_be_visible()
        check("Rounded equality explained without suppressing warning", True,
              "未舍入" in page.locator(".rounding-note").inner_text())
        page.unroute("**/api/portfolio")
        page.goto(url+"/#simulate")
        page.reload()
        expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
        pending_simulation=[]
        page.route("**/api/simulations", lambda route: pending_simulation.append(route))
        page.get_by_role("button",name="添加并计算").click()
        page.wait_for_timeout(100)
        check("Calculation loading label and disabled submit", True,
              "正在校验" in page.locator("#trade-form button").inner_text() and page.locator("#trade-form button").is_disabled())
        held = pending_simulation.pop()
        page.get_by_role("link",name="组合概览").click()
        page.get_by_role("link",name="调仓模拟",exact=False).first.click()
        expect(page.get_by_role("heading",name="调仓模拟",exact=True)).to_be_visible()
        check("Navigation preserves in-flight lock", True, page.locator("#trade-form button").is_disabled())
        held.fulfill(response=held.fetch())
        page.unroute("**/api/simulations")
        expect(page.locator(".steps li")).to_have_count(1)
        check("Late calculation commits once", True, page.locator(".steps li").count()==1)
        page.screenshot(path=str(ROOT / "output/playwright/08-review-simulation.png"),full_page=True)
    check("No uncaught page errors", [], errors)
    name = "review-before.json" if probe else "review-browser-results.json"
    report = {"executed_at":datetime.now(timezone.utc).isoformat(),"browser":browser.version,
              "checks":checks,"all_passed":all(c["passed"] for c in checks),
              "source_version":"original submission" if source_root != ROOT else "current working tree",
              "source_sha256":{p.relative_to(source_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                               for folder in ["frontend","backend"] for p in sorted((source_root/folder).glob("*")) if p.is_file()}}
    (ROOT / "output/verification" / name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    context.close(); browser.close()

if not probe and not report["all_passed"]: sys.exit(1)
