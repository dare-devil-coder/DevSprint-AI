/** DevSprint AI browser state, approval checkpoint, and live agent updates. */
import { renderArchify } from "./archify.js";
import { renderChat } from "./chat.js";
import { renderTimeline, setAgentStatus } from "./timeline.js";
import { loadFiles, loadFile } from "./viewer.js";
import { connectStatus } from "./websocket.js";

const state = { project: {}, contract: null, plan: null, approvalEditing: false };
const approval = document.getElementById("approval-modal");
const approvalMessage = document.getElementById("approval-message");
const editButton = document.getElementById("edit-contract");
const approveButton = document.getElementById("approve-build");
const editor = document.getElementById("approval-edit");
const contractView = document.getElementById("approval-contract");
const archifyDialog = document.getElementById("archify-dialog");

/** Read JSON and expose a specific server error when available. */
async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not load " + path + ".");
  return data;
}

/** Send JSON to one project endpoint and surface validation errors. */
async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(detail || "The request could not be completed.");
  }
  return data;
}

/** Update the durable state across chat, timeline, and file viewer. */
function update(project) {
  state.project = project;
  renderChat(project, startProject, submitAnswer);
  renderTimeline(project);
  loadFiles();
  if (project.phase === "awaiting_approval" && !approval.open) showApproval();
  if (!["awaiting_approval", "planning"].includes(project.phase) && approval.open) {
    approval.close();
  }
}

/** Build the Quiet review column from the saved file and acceptance plan. */
function renderPlan(plan) {
  const container = document.getElementById("approval-plan");
  container.replaceChildren();
  const stack = document.createElement("p");
  stack.className = "approval-modal__stack";
  stack.textContent = "Python · " + (plan.tech_stack?.libraries?.join(", ") || "standard library");
  container.append(stack);
  (plan.file_structure || []).forEach((file) => {
    const row = document.createElement("div");
    row.className = "approval-modal__file";
    const name = document.createElement("strong");
    name.textContent = file.path;
    const purpose = document.createElement("span");
    purpose.textContent = file.purpose;
    row.append(name, purpose);
    container.append(row);
  });
  const criteria = document.createElement("ul");
  criteria.className = "approval-modal__criteria";
  (plan.acceptance_criteria || []).forEach((item) => {
    const entry = document.createElement("li");
    entry.textContent = item.feature;
    criteria.append(entry);
  });
  container.append(criteria);
}

/** Fetch and display both artifacts when the pipeline pauses for approval. */
async function showApproval(contract = null, plan = null) {
  approvalMessage.textContent = "Loading contract and architecture…";
  try {
    const readyContract = contract || JSON.parse((await getJson("/api/project/file/contract.json")).content);
    const readyPlan = plan || await getJson("/api/project/plan");
    state.contract = readyContract;
    state.plan = readyPlan;
    contractView.textContent = JSON.stringify(readyContract, null, 2);
    editor.value = JSON.stringify(readyContract, null, 2);
    editor.hidden = true;
    contractView.hidden = false;
    state.approvalEditing = false;
    editButton.textContent = "Edit Contract";
    renderPlan(readyPlan);
    if (!approval.open) approval.showModal();
    renderArchify(document.getElementById("approval-archify"), readyContract, readyPlan);
    approvalMessage.textContent = "No code runs until you approve.";
  } catch (error) {
    approvalMessage.textContent = error.message;
  }
}

/** Begin clarification for the idea entered in chat. */
export async function startProject(idea) {
  state.contract = null;
  state.plan = null;
  update(await post("/api/project/start", { idea }));
}

/** Store one answer and reveal the next question or planning state. */
export async function submitAnswer(answer) {
  update(await post("/api/project/answer", { answer }));
}

/** Toggle contract editing or save edits and regenerate the plan. */
async function editContract() {
  if (!state.approvalEditing) {
    state.approvalEditing = true;
    editor.hidden = false;
    contractView.hidden = true;
    editButton.textContent = "Save changes";
    approvalMessage.textContent = "Save the edited JSON to refresh the architecture plan.";
    editor.focus();
    return;
  }
  editButton.disabled = true;
  approvalMessage.textContent = "Updating architecture plan…";
  try {
    const edited = JSON.parse(editor.value);
    const project = await post("/api/project/contract", edited);
    update(project);
    await showApproval();
  } catch (error) {
    approvalMessage.textContent = error.message;
  } finally {
    editButton.disabled = false;
  }
}

/** Approve the reviewed contract and start the code-generation pipeline. */
async function approveBuild() {
  if (state.approvalEditing) {
    approvalMessage.textContent = "Save your contract changes before approving.";
    return;
  }
  approveButton.disabled = true;
  approveButton.textContent = "Starting build…";
  approvalMessage.textContent = "Starting the approved build…";
  try {
    update(await post("/api/project/approve", { approved: true }));
    approval.close();
  } catch (error) {
    approvalMessage.textContent = error.message;
  } finally {
    approveButton.disabled = false;
    approveButton.textContent = "Approve & Build";
  }
}

/** Open the architecture diagrams from the center timeline panel. */
async function openArchitecture() {
  try {
    if (!state.contract || !state.plan) {
      state.contract = JSON.parse((await getJson("/api/project/file/contract.json")).content);
      state.plan = await getJson("/api/project/plan");
    }
    archifyDialog.showModal();
    renderArchify(document.getElementById("architecture-archify"), state.contract, state.plan);
  } catch (error) {
    document.getElementById("phase-copy").textContent = error.message;
  }
}

/** Load current project state when the page opens or refreshes. */
async function initialize() {
  try {
    update(await getJson("/api/project/status"));
  } catch (error) {
    update({});
    document.getElementById("viewer-message").textContent = error.message;
  }
  connectStatus();
}

approval.addEventListener("cancel", (event) => {
  if (state.project.phase === "awaiting_approval") event.preventDefault();
});
editButton.addEventListener("click", editContract);
approveButton.addEventListener("click", approveBuild);
document.getElementById("open-archify").addEventListener("click", openArchitecture);
document.getElementById("close-archify").addEventListener("click", () => archifyDialog.close());
document.addEventListener("agent-status", (event) => {
  setAgentStatus(event.detail, state.project);
  loadFiles();
});
document.addEventListener("project-status", (event) => update(event.detail));
document.addEventListener("contract-ready", (event) =>
  showApproval(event.detail.contract, event.detail.plan));
document.addEventListener("verification-ready", () => {
  loadFiles();
  loadFile("Verification");
});
document.addEventListener("files-updated", () => loadFiles());
document.addEventListener("output", () => loadFile("Output"));
initialize();
