# FastAPI endpoints, WebSocket status stream, and static frontend.
"""FastAPI endpoints, WebSocket status stream, and static frontend."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.memory.shared_memory import (
    CONTRACT_FILE, ERRORS_FILE, OUTPUT_FILE, PLAN_FILE, SERPAPI_LOG_FILE,
    VERIFICATION_FILE, WORKSPACE_DIR, read_json,
)
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
        name = read_json(CONTRACT_FILE).get("project_name", "")
        root = WORKSPACE_DIR / name
        if root.is_dir():
            files.extend(f"{name}/{file.name}" for file in root.iterdir()
                         if file.is_file() and file.name in {"main.py", "test_main.py", "README.md"})
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
    if not name or path not in {f"{name}/main.py", f"{name}/test_main.py",
                              f"{name}/README.md"}:
        raise HTTPException(status_code=404, detail="File not found.")
    target = WORKSPACE_DIR / path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


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
