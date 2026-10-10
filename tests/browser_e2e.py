# Drive the complete DevSprint UI in Chromium and save reproducible evidence.
"""Browser-level approval, build, verification, and search-log test."""

from __future__ import annotations

import argparse
import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


def screenshot(page: Page, target: Path) -> None:
    """Save one full-page screenshot after creating its parent directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=True)


def main() -> int:
    """Run the browser scenario and write a result even when a step fails."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--log-path", default="memory/serpapi_log.json")
    parser.add_argument("--output", default="demo_evidence")
    parser.add_argument("--mode", choices=("live", "mocked"), default="live")
    parser.add_argument("--reset-isolated", action="store_true",
                        help="Reset only the test server on port 8001 or 8002")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    screenshots: list[str] = []
    step = "launch"
    passed = 0
    total = 13
    calls = 0
    blocking_errors: list[str] = []
    page = None
    browser = None
    playwright = None

    try:
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=False)
        except Exception as error:
            print(f"Visible Chromium unavailable ({error}); retrying headless.")
            browser = playwright.chromium.launch(headless=True)
        passed += 1
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda message: console_errors.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        step = "open"
        if args.reset_isolated:
            root, port = ((Path("demo_evidence/runtime"), 8001) if args.mode == "mocked"
                          else (Path("demo_evidence/live_runtime"), 8002))
            if (urlparse(args.base_url).port != port
                    or not Path(args.log_path).resolve().is_relative_to(root.resolve())):
                raise ValueError("--reset-isolated requires the matching isolated test server and log path")
            reset = page.request.post(args.base_url + "/api/demo/reset", timeout=15000)
            assert reset.status == 200, f"Isolated demo reset failed: HTTP {reset.status}"
        response = page.goto(args.base_url, wait_until="networkidle", timeout=15000)
        assert response and response.status == 200, "Homepage did not return HTTP 200"
        passed += 1

        step = "panels"
        for panel in (".panel--chat", ".panel--timeline", ".panel--viewer"):
            assert page.locator(panel).is_visible(), f"Panel is hidden: {panel}"
        passed += 1

        step = "idea"
        page.locator(".chat__form textarea").fill(
            "Build me a CLI tool that converts Celsius to Fahrenheit."
        )
        passed += 1

        step = "start"
        page.get_by_role("button", name=re.compile("Start project", re.I)).click()
        passed += 1

        answers = [
            "A Python command-line tool.",
            "Run a command with one Celsius number and convert that value.",
            "A learner uses it; accept a Celsius number and print the Fahrenheit result.",
            "Reject non-numeric input and explain invalid values clearly.",
        ]
        step = "questions"
        page.locator(".chat__form--answer textarea").wait_for(timeout=15000)
        passed += 1

        step = "answers"
        for answer in answers:
            field = page.locator(".chat__form--answer textarea")
            field.wait_for(timeout=15000)
            field.fill(answer)
            page.get_by_role("button", name=re.compile("Send answer", re.I)).click()
            page.wait_for_timeout(250)
        for _ in range(8):
            if not page.locator(".chat__form--answer textarea").count():
                break
            page.locator(".chat__form--answer textarea").fill("Use reasonable defaults.")
            page.get_by_role("button", name=re.compile("Send answer", re.I)).click()
            page.wait_for_timeout(250)
        passed += 1

        step = "approval"
        page.locator("#approval-modal[open]").wait_for(timeout=120000)
        assert page.locator("#approval-contract").inner_text().strip()
        assert page.locator("#approval-plan").inner_text().strip()
        passed += 1

        step = "approval_screenshot"
        screenshot(page, output / "01_approval_modal.png")
        screenshots.append("01_approval_modal.png")
        passed += 1

        step = "approve_and_build"
        page.get_by_role("button", name="Approve & Build").click()
        page.locator("#approval-modal[open]").wait_for(state="hidden", timeout=15000)
        passed += 1

        step = "pipeline_complete"
        page.locator("#header-status").get_by_text("Build complete").wait_for(timeout=180000)
        screenshot(page, output / "02_pipeline_complete.png")
        screenshots.append("02_pipeline_complete.png")
        passed += 1

        step = "verification"
        page.get_by_role("tab", name="Verification", exact=True).click()
        page.locator("#viewer-verification").get_by_text(
            re.compile("pass|verified", re.I)
        ).first.wait_for(timeout=15000)
        report_response = page.request.get(args.base_url + "/api/verification/report")
        assert report_response.status == 200 and report_response.json(), (
            "The documented verification report endpoint is empty or unavailable"
        )
        screenshot(page, output / "03_verification.png")
        screenshots.append("03_verification.png")
        passed += 1

        step = "serpapi_log"
        log = json.loads(Path(args.log_path).read_text(encoding="utf-8"))
        calls = len(log.get("calls", []))
        assert any(item.get("results_count", 0) > 0 for item in log.get("calls", [])), (
            "No SerpApi log entry has results_count > 0"
        )
        page.get_by_role("tab", name="SerpApi Log").click()
        page.locator("#viewer-content").get_by_text("results_count").wait_for(timeout=15000)
        screenshot(page, output / "04_serpapi_log.png")
        screenshots.append("04_serpapi_log.png")
        passed += 1
    except Exception as error:
        details = f"{step}: {type(error).__name__}: {error}"
        blocking_errors.append(details)
        print(details)
        traceback.print_exc()
        if page is not None:
            try:
                filename = f"FAILED_{step}.png"
                screenshot(page, output / filename)
                screenshots.append(filename)
            except Exception as capture_error:
                print(f"Failure screenshot unavailable: {capture_error}")
        print("Browser console errors:", json.dumps(console_errors, indent=2))
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        report = [
            "# Browser E2E Result", "",
            f"- Timestamp: {datetime.now(timezone.utc).isoformat()}",
            f"- Mode: {args.mode}",
            f"- Steps passed: {passed}/{total}",
            f"- SerpApi calls logged: {calls}",
            f"- Screenshots saved: {screenshots}",
            f"- Blocking errors: {blocking_errors or 'none'}",
            f"- Browser console errors: {console_errors or 'none'}",
        ]
        if args.mode == "mocked":
            report.append("- Evidence limit: Model and SerpApi responses are deterministic test fixtures; no live external API call was verified.")
        (output / "RESULT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print("\n".join(report))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
