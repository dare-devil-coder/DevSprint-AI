"""Ensure approved builds can be resumed after a recoverable error state."""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    resumed: list[bool] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/project/status", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({
                "idea": "StudyFlow", "answers": [], "phase": "error", "agent": "Coder",
                "approved": True, "is_running": False,
                "message": "Build stopped after a temporary provider failure.",
                "completed_agents": ["Coder", "Test Writer", "Executor"],
            })))
        page.route("**/api/project/files", lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"files":[]}'))

        def resume(route):
            resumed.append(True)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "idea": "StudyFlow", "answers": [], "phase": "building", "agent": "Test Writer",
                "approved": True, "is_running": True, "message": "Resuming the approved build.",
            }))

        page.route("**/api/project/resume", resume)
        page.route_web_socket("**/ws/status", lambda socket: None)
        try:
            page.goto(args.base_url, wait_until="networkidle", timeout=20000)
            button = page.get_by_role("button", name="Resume build")
            button.wait_for(state="visible")
            button.click()
            page.get_by_text("Resuming the approved build.").wait_for()
            assert resumed == [True]
            print("PASS: an approved build in error state offers Resume build and calls the resume API.")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
