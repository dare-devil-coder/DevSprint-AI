"""Exercise a generated browser prototype in the real project viewer iframe."""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright


PREVIEW_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Task board</title></head><body><main><h1>Task board</h1><p id="count">0 tasks</p><button id="add-task" type="button">Add task</button><button id="delete-task" type="button">Delete task</button></main><script>(()=>{const project="reading_tracker",values=new Map(),dirty=new Set();const storage={getItem:k=>values.get(String(k))??null,setItem(k,v){k=String(k);v=String(v);values.set(k,v);dirty.add(k);parent.postMessage({type:"devsprint-preview-storage-set",project,key:k,value:v},"*")},removeItem(k){k=String(k);values.delete(k);dirty.add(k);parent.postMessage({type:"devsprint-preview-storage-remove",project,key:k},"*")},clear(){values.clear();dirty.add("*");parent.postMessage({type:"devsprint-preview-storage-clear",project},"*")},key:i=>[...values.keys()][i]??null,get length(){return values.size}};Object.defineProperty(window,"localStorage",{value:storage});addEventListener("message",e=>{if(e.source!==parent||e.data?.type!=="devsprint-preview-storage-init"||e.data.project!==project)return;for(const [k,v] of e.data.entries||[])if(!dirty.has("*")&&!dirty.has(k))values.set(k,v)});parent.postMessage({type:"devsprint-preview-storage-ready",project},"*")})();</script><script>addEventListener("message",function boot(e){if(e.source!==parent||e.data?.type!=="devsprint-preview-storage-init")return;removeEventListener("message",boot);let total=Number(localStorage.getItem("total")||0);const count=document.querySelector("#count");count.textContent=`${total} tasks`;document.querySelector("#add-task").addEventListener("click",()=>{total+=1;localStorage.setItem("total",String(total));count.textContent=`${total} tasks`;});document.querySelector("#delete-task").addEventListener("click",()=>{if(confirm("Delete all tasks?")){total=0;localStorage.removeItem("total");count.textContent="0 tasks";}});});</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        api_requests: list[str] = []
        page.on("request", lambda request: api_requests.append(request.url)
                if "/api/project/" in request.url else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/project/status", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({
                "idea": "Build a task board website", "answers": [], "phase": "complete",
                "project_type": "web_app",
            })))
        page.route("**/api/project/files", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"files": [
                "contract.json", "plan.json", "reading_tracker/index.html",
                "reading_tracker/styles.css", "reading_tracker/app.js", "Preview",
            ]})))
        page.route("**/api/project/file/contract.json", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"content": json.dumps({"project_name": "reading_tracker"})})))
        page.route("**/api/project/preview*", lambda route: route.fulfill(
            status=200, content_type="text/html", body=PREVIEW_HTML))
        page.route_web_socket("**/ws/status", lambda socket: None)
        try:
            page.goto(args.base_url, wait_until="networkidle", timeout=20000)
            page.evaluate("localStorage.setItem('__devsprint_preview__:reading_tracker:total', '4')")
            page.wait_for_timeout(500)
            preview_tab = page.get_by_role("tab", name="Preview", exact=True)
            if not preview_tab.count():
                raise AssertionError({"tabs": page.locator("#viewer-tabs").inner_text(),
                                      "message": page.locator("#viewer-message").inner_text(),
                                      "errors": errors, "api_requests": api_requests})
            preview_tab.wait_for(state="visible")
            preview_tab.click()
            frame = page.frame_locator("#viewer-preview")
            frame.get_by_role("heading", name="Task board").wait_for()
            frame.get_by_text("4 tasks", exact=True).wait_for()
            assert frame.locator("#count").inner_text() == "4 tasks"
            frame.get_by_role("button", name="Add task").click()
            assert frame.locator("#count").inner_text() == "5 tasks"
            assert page.evaluate("localStorage.getItem('__devsprint_preview__:reading_tracker:total')") == "5"
            page.get_by_role("tab", name="contract.json").click()
            preview_tab.click()
            frame.locator("#count").wait_for()
            frame.get_by_text("5 tasks", exact=True).wait_for()
            assert frame.locator("#count").inner_text() == "5 tasks"
            page.once("dialog", lambda dialog: dialog.accept())
            frame.get_by_role("button", name="Delete task").click()
            assert frame.locator("#count").inner_text() == "0 tasks"
            assert page.evaluate("localStorage.getItem('__devsprint_preview__:reading_tracker:total')") is None
            assert not errors, errors
            print("PASS: generated preview loads in the viewer and its interaction works.")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
