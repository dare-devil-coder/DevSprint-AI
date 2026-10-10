# Check the saved DevSprint page at narrow browser widths without changing app state.
"""Responsive browser spot check for the completed project view."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    """Assert all three panels remain reachable without horizontal overflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--output", default="demo_evidence")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.goto(args.base_url, wait_until="networkidle", timeout=15000)
            for width in (390, 320):
                page.set_viewport_size({"width": width, "height": 844})
                for panel in (".panel--chat", ".panel--timeline", ".panel--viewer"):
                    assert page.locator(panel).is_visible(), f"{panel} hidden at {width}px"
                actual = page.evaluate("document.documentElement.scrollWidth")
                assert actual <= width, f"Horizontal overflow at {width}px: {actual}px"
                page.screenshot(path=str(output / f"0{5 if width == 390 else 6}_mobile_{width}.png"),
                                full_page=True)
                print(f"{width}px: all panels visible; document width {actual}px")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
