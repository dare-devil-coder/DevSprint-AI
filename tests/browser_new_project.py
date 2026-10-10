"""Browser check for starting a project from the webpage without calling the real API."""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    started: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route("**/api/project/status", lambda route: route.fulfill(
            status=200, content_type="application/json",
            # A persisted in-progress phase may be stale after the server restarts.
            body=json.dumps({"idea": "Existing project", "answers": [], "phase": "planning"}),
        ))
        page.route("**/api/project/files", lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"files":[]}'))
        page.route("**/api/project/start", lambda route: (
            started.append(json.loads(route.request.post_data or "{}")),
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "idea": (json.loads(route.request.post_data or "{}")).get("idea", ""),
                "answers": [], "phase": "questions", "question": "What inputs should it accept?",
            })),
        ))
        page.route_web_socket("**/ws/status", lambda socket: None)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(args.base_url, wait_until="networkidle", timeout=20000)
            page.set_viewport_size({"width": 320, "height": 844})
            button = page.get_by_role("button", name="+ New Project")
            button.wait_for(state="visible")
            assert button.is_enabled()
            assert page.evaluate("document.documentElement.scrollWidth") <= 320
            button.click()
            dialog = page.get_by_role("dialog", name="Start a new project")
            dialog.wait_for(state="visible")
            bounds = dialog.bounding_box()
            assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 320, bounds
            dialog.locator("#new-project-idea").fill("Create a simple unit converter")
            dialog.get_by_role("button", name="Start project").click()
            dialog.wait_for(state="hidden")
            page.get_by_text("What inputs should it accept?").wait_for(state="visible")
            assert started == [{"idea": "Create a simple unit converter"}], started
            assert not errors, errors
            print("PASS: webpage opens the new-project form, submits the idea, and displays the first clarification question.")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
