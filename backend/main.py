# FastAPI endpoints, WebSocket status stream, and static frontend.
"""FastAPI endpoints, WebSocket status stream, and static frontend."""

from pathlib import Path
import json
import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.memory.shared_memory import (
    CONTRACT_FILE, ERRORS_FILE, OUTPUT_FILE, PLAN_FILE, SERPAPI_LOG_FILE,
    VERIFICATION_FILE, WORKSPACE_DIR, SETTINGS_FILE, read_json, write_json,
)
from backend.memory.project_details import (
    generate as generate_details, list_details, read_detail,
)
from backend.skills.skill_manager import skill_manager
from backend.orchestrator import orchestrator
from backend.websocket_manager import websocket_manager

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
app = FastAPI(title="DevSprint AI", version="1.0.0")


class StartRequest(BaseModel):
    """A new project idea submitted from the chat."""

    idea: str = Field(min_length=3, max_length=4000)


class AnswerRequest(BaseModel):
    """One answer to the current requirements question."""

    answer: str = Field(min_length=1, max_length=4000)


class ApprovalRequest(BaseModel):
    """An explicit approval decision for the reviewed contract and plan."""

    approved: bool


class ContractEditRequest(BaseModel):
    """An edited contract submitted before the build is approved."""

    app_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    inputs: list[str]
    outputs: list[str]
    edge_cases: list[str]
    project_type: Literal["web_app", "python_cli"] = "python_cli"
    design_direction: str = ""


class SettingsRequest(BaseModel):
    """User choices persisted for the next generated project."""

    generate_project_details: bool = False
    skill_level: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")


class DeeperRequest(BaseModel):
    """The requested on-demand explanation level."""

    level: int = Field(ge=3, le=4)


@app.get("/api/skills")
async def skills() -> dict[str, Any]:
    """List built-in skill metadata without exposing their prompt bodies."""
    return {"skills": skill_manager.list_skills()}


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    """Read settings with safe defaults before the first save."""
    return {"generate_project_details": False, "skill_level": "beginner",
            **read_json(SETTINGS_FILE, {})}


@app.post("/api/settings")
async def save_settings(payload: SettingsRequest) -> dict[str, Any]:
    """Persist the learner settings for subsequent project runs."""
    settings = payload.model_dump()
    write_json(SETTINGS_FILE, settings)
    return settings


@app.get("/api/project/details")
async def project_details_list() -> dict[str, list[str]]:
    """List only explanations generated for the active project."""
    return {"files": list_details()}


@app.get("/api/project/details/{name}")
async def project_details_file(name: str) -> dict[str, str]:
    """Read one allowlisted explanation file."""
    content = read_detail(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Explanation not found.")
    return {"name": name, "content": content}


@app.post("/api/project/details/deeper")
async def project_details_deeper(payload: DeeperRequest) -> dict[str, list[str]]:
    """Generate level three or four only after a learner asks for it."""
    if not (await get_settings())["generate_project_details"]:
        raise HTTPException(status_code=409, detail="Enable Project Details in settings first.")
    try:
        files = await generate_details(payload.level)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"files": files}


@app.post("/api/demo/reset")
async def demo_reset() -> dict[str, str]:
    """Clear generated project data before starting a clean presentation."""
    try:
        return await orchestrator.demo_reset()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/project/start")
async def start_project(payload: StartRequest) -> dict[str, Any]:
    """Start one project clarification session."""
    try:
        return await orchestrator.start(payload.idea)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/project/answer")
async def answer_project(payload: AnswerRequest) -> dict[str, Any]:
    """Answer the active question and advance the pipeline."""
    try:
        return await orchestrator.answer(payload.answer)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/project/approve")
async def approve_project(payload: ApprovalRequest) -> dict[str, Any]:
    """Resume the pipeline after the user approves the saved artifacts."""
    try:
        return await orchestrator.approve(payload.approved)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/project/resume")
async def resume_project() -> dict[str, Any]:
    """Restart an approved build after a development-server reload."""
    try:
        return await orchestrator.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/project/contract")
async def edit_project_contract(payload: ContractEditRequest) -> dict[str, Any]:
    """Save contract edits and rebuild the architecture plan before approval."""
    try:
        return await orchestrator.edit_contract(payload.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/project/status")
async def project_status() -> dict[str, Any]:
    """Read the current project and question state."""
    return orchestrator.status()


@app.get("/api/project/plan")
async def project_plan() -> dict[str, Any]:
    """Read the saved architecture plan."""
    return read_json(PLAN_FILE)


@app.get("/api/project/verification")
async def project_verification() -> dict[str, Any]:
    """Read the current per-layer verification report."""
    return read_json(VERIFICATION_FILE)


@app.get("/api/verification/report")
async def verification_report() -> dict[str, Any]:
    """Expose the documented verification-report route."""
    return await project_verification()


@app.get("/api/project/files")
async def project_files() -> dict[str, list[str]]:
    """List only the saved contract and files from the active generated project."""
    files: list[str] = []
    if read_json(CONTRACT_FILE):
        files.append("contract.json")
        if read_json(PLAN_FILE):
            files.append("plan.json")
        if read_json(VERIFICATION_FILE):
            files.append("verification.json")
        contract = read_json(CONTRACT_FILE)
        name = contract.get("project_name", "")
        root = WORKSPACE_DIR / name
        plan_files = {item.get("path") for item in read_json(PLAN_FILE, {}).get("file_structure", [])
                      if isinstance(item, dict) and isinstance(item.get("path"), str)}
        plan_files.add("README.md")
        if root.is_dir():
            files.extend(f"{name}/{relative}" for relative in sorted(plan_files)
                         if (root / relative).is_file())
            if contract.get("project_type") == "web_app" and (root / "index.html").is_file():
                files.append("Preview")
    return {"files": files}


@app.get("/api/project/file/{path:path}")
async def project_file(path: str) -> dict[str, str]:
    """Read an allowlisted generated file without path traversal."""
    contract = read_json(CONTRACT_FILE)
    name = contract.get("project_name")
    saved_files = {"contract.json": CONTRACT_FILE, "plan.json": PLAN_FILE,
                   "verification.json": VERIFICATION_FILE}
    if path in saved_files and read_json(saved_files[path]):
        return {"path": path, "content": saved_files[path].read_text(encoding="utf-8")}
    plan_files = {item.get("path") for item in read_json(PLAN_FILE, {}).get("file_structure", [])
                  if isinstance(item, dict) and isinstance(item.get("path"), str)}
    plan_files.add("README.md")
    prefix = f"{name}/" if name else ""
    relative = path.removeprefix(prefix) if prefix and path.startswith(prefix) else ""
    if not name or relative not in plan_files:
        raise HTTPException(status_code=404, detail="File not found.")
    target = WORKSPACE_DIR / name / relative
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


@app.get("/api/project/preview", response_class=HTMLResponse)
async def project_preview() -> HTMLResponse:
    """Inline approved local web assets for a self-contained, sandboxed browser preview."""
    contract = read_json(CONTRACT_FILE)
    if contract.get("project_type") != "web_app":
        raise HTTPException(status_code=404, detail="This project has no browser preview.")
    plan_files = {item.get("path") for item in read_json(PLAN_FILE, {}).get("file_structure", [])
                  if isinstance(item, dict) and isinstance(item.get("path"), str)}
    if not {"index.html", "styles.css", "app.js"}.issubset(plan_files):
        raise HTTPException(status_code=404, detail="The approved plan has no complete browser preview.")
    root = WORKSPACE_DIR / contract["project_name"]
    try:
        html = (root / "index.html").read_text(encoding="utf-8")
        css = (root / "styles.css").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Preview files are not ready.") from exc
    html, stylesheet_count = re.subn(
        r"<link\b(?=[^>]*\bhref=[\"'][^\"']*styles\.css(?:\?[^\"']*)?[\"'])[^>]*>",
        lambda _: "<style>\n" + re.sub(r"</style", r"<\\/style", css, flags=re.I) + "\n</style>",
        html, count=1, flags=re.I,
    )
    html, script_count = re.subn(
        r"<script\b(?=[^>]*\bsrc=[\"'][^\"']*app\.js(?:\?[^\"']*)?[\"'])[^>]*>\s*</script>",
        "<!-- DEVSprint_APP_JS -->",
        html, count=1, flags=re.I,
    )
    if not stylesheet_count or not script_count:
        raise HTTPException(status_code=422, detail="The preview page must link styles.css and app.js.")
    storage_bridge = """<script>
(() => {
  const project = __PROJECT_NAME__;
  const values = new Map();
  const dirty = new Set();
  let started = false;
  const startApp = () => {
    if (started) return;
    started = true;
    const script = document.createElement("script");
    script.textContent = __APP_CODE__;
    document.body.append(script);
  };
  const notify = (type, key, value) => parent.postMessage(
    { type: "devsprint-preview-storage-" + type, project, key, value }, "*");
  const isolatedStorage = {
    getItem(key) { const value = values.get(String(key)); return value === undefined ? null : value; },
    setItem(key, value) { key = String(key); value = String(value); values.set(key, value); dirty.add(key); notify("set", key, value); },
    removeItem(key) { key = String(key); values.delete(key); dirty.add(key); notify("remove", key); },
    clear() { values.clear(); dirty.add("*"); notify("clear"); },
    key(index) { return [...values.keys()][index] ?? null; },
    get length() { return values.size; }
  };
  try { window.localStorage.getItem("__devsprint_preview_probe__"); }
  catch { Object.defineProperty(window, "localStorage", { value: isolatedStorage }); }
  window.addEventListener("message", event => {
    const data = event.data;
      if (event.source !== parent || data?.type !== "devsprint-preview-storage-init" || data.project !== project) return;
    for (const [key, value] of data.entries || []) {
        if (!dirty.has("*") && !dirty.has(key) && typeof key === "string" && typeof value === "string") values.set(key, value);
    }
      startApp();
  });
  parent.postMessage({ type: "devsprint-preview-storage-ready", project }, "*");
    setTimeout(startApp, 200);
})();
</script>""".replace("__PROJECT_NAME__", json.dumps(contract["project_name"]).replace("<", "\\u003c"))
    safe_app_code = json.dumps(js).replace("<", "\\u003c")
    script_markup = storage_bridge.replace("__APP_CODE__", safe_app_code)
    if "<!-- DEVSprint_APP_JS -->" not in html:
        raise HTTPException(status_code=422, detail="The preview page must load app.js.")
    html = html.replace("<!-- DEVSprint_APP_JS -->", script_markup, 1)
    return HTMLResponse(html, headers={
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; "
            "form-action 'none'; base-uri 'none'; object-src 'none'"),
    })


@app.get("/api/project/errors")
async def project_errors() -> dict[str, Any]:
    """Read execution and agent errors for the current project."""
    return {"errors": read_json(ERRORS_FILE, [])}


@app.get("/api/project/output")
async def project_output() -> dict[str, Any]:
    """Read the most recent program and test output."""
    return read_json(OUTPUT_FILE)


@app.get("/api/project/serpapi-log")
async def serpapi_log() -> dict[str, Any]:
    """Read the audit log of SerpApi cache hits and network calls."""
    return read_json(SERPAPI_LOG_FILE, {"calls": []})


@app.websocket("/ws/status")
async def status_socket(websocket: WebSocket) -> None:
    """Keep a browser subscribed to live agent and project events."""
    await websocket_manager.connect(websocket)
    await websocket.send_json({"type": "project-status", **orchestrator.status()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


@app.get("/")
async def index() -> FileResponse:
    """Serve the app shell."""
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
