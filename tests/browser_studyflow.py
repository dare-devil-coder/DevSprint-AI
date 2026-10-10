"""Exercise the generated StudyFlow prototype in Chromium without a server."""

from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT = Path(__file__).resolve().parents[1] / "workspace" / "studyflow"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((PROJECT / "index.html").as_uri(), wait_until="load")
        page.evaluate("localStorage.clear()")
        page.reload(wait_until="load")

        assert page.locator("#total-count").inner_text() == "Total: 3"
        page.locator("#title").fill("Prepare presentation")
        page.locator("#course").fill("Physics")
        page.locator("#dueDate").fill("2026-10-20")
        page.locator("#priority").fill("5")
        page.get_by_role("button", name="Add Task").click()
        assert page.locator("#total-count").inner_text() == "Total: 4"
        page.locator("#filter-select").select_option("completed")
        assert page.locator(".task-card").count() == 1
        page.locator("#filter-select").select_option("all")
        target = page.locator(".task-card").filter(has_text="Prepare presentation")
        target.get_by_role("button", name="Mark Complete").click()
        assert page.locator("#completed-count").inner_text() == "Completed: 2"
        page.reload(wait_until="load")
        assert page.get_by_text("Prepare presentation", exact=True).count() == 1
        assert page.locator("#completed-count").inner_text() == "Completed: 2"

        page.locator("#title").fill("")
        page.locator("#course").fill("")
        page.get_by_role("button", name="Add Task").click()
        assert "Title is required." in page.locator("#validation-messages").inner_text()
        assert page.locator("#total-count").inner_text() == "Total: 4"

        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        while page.locator(".task-card").count():
            page.locator(".task-card").first.get_by_role("button", name="Delete").click()
        assert page.locator("#total-count").inner_text() == "Total: 0"
        assert page.locator("#empty-state").is_visible()
        page.reload(wait_until="load")
        assert page.locator("#total-count").inner_text() == "Total: 0"
        assert page.locator("#empty-state").is_visible()
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
    print("PASS: StudyFlow add, filter, complete, persist, delete, and empty-state flows work at desktop and mobile widths.")
