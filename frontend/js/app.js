/** DevSprint AI browser state, approval checkpoint, and live agent updates. */
import { renderArchify } from "./archify.js";
import { addSystemMessage, clearSystemMessages, renderChat, setSampleIdea } from "./chat.js";
import { renderTimeline, setAgentStatus } from "./timeline.js";
import { loadFiles, loadFile, resetViewer } from "./viewer.js";
import { connectStatus } from "./websocket.js";
import { loadSettings, openSettings } from "./settings.js";
import { loadSkillMetadata, setActiveSkills } from "./skills.js";

const state = { project: {}, contract: null, plan: null, approvalEditing: false };
const approval = document.getElementById("approval-modal");
const approvalMessage = document.getElementById("approval-message");
const editButton = document.getElementById("edit-contract");
const approveButton = document.getElementById("approve-build");
const retryApprovalButton = document.getElementById("retry-approval");
const editor = document.getElementById("approval-edit");
const contractView = document.getElementById("approval-contract");
const archifyDialog = document.getElementById("archify-dialog");
const demoDialog = document.getElementById("demo-dialog");
const demoMessage = document.getElementById("demo-message");
const demoButton = document.getElementById("confirm-demo");
const newProjectDialog = document.getElementById("new-project-dialog");
const newProjectForm = document.getElementById("new-project-form");
const newProjectIdea = document.getElementById("new-project-idea");
const newProjectMessage = document.getElementById("new-project-message");
const newProjectButton = document.getElementById("new-project");
const submitNewProjectButton = document.getElementById("submit-new-project");
const resumeBuildButton = document.getElementById("resume-build");
const sampleIdea = "Build me a CLI tool that converts Celsius to Fahrenheit";

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
  if (project.phase === "planning" && state.project.phase === "awaiting_approval" &&
      project.idea === state.project.idea) return;
  state.project = project;
  // Persisted phases can outlive a server restart; let the API decide whether a run is still active.
  newProjectButton.disabled = false;
  newProjectButton.title = "Start a new project in the browser.";
  renderChat(project, startProject, submitAnswer);
  renderTimeline(project);
  resumeBuildButton.hidden = !(project.approved && project.is_running === false &&
    ["building", "error"].includes(project.phase));
  if (Array.isArray(project.active_skills)) setActiveSkills(project.active_skills);
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
  stack.textContent = plan.project_type === "web_app"
    ? "Browser prototype · HTML, CSS, JavaScript"
    : "Python CLI · " + (plan.tech_stack?.libraries?.join(", ") || "standard library");
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
  approveButton.disabled = true;
  retryApprovalButton.hidden = true;
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
    approveButton.disabled = false;
    update(await getJson("/api/project/status"));
  } catch (error) {
    approvalMessage.textContent = error.message;
    retryApprovalButton.hidden = false;
    if (!approval.open) approval.showModal();
  }
}

/** Begin clarification for the idea entered in chat. */
export async function startProject(idea) {
  clearSystemMessages();
  setActiveSkills([]);
  document.getElementById("demo-banner").hidden = true;
  state.contract = null;
  state.plan = null;
  update(await post("/api/project/start", { idea }));
}

/** Store one answer and reveal the next question or planning state. */
export async function submitAnswer(answer) {
  update(await post("/api/project/answer", { answer }));
}

/** Resume an approved build that was interrupted by a server restart. */
async function resumeBuild() {
  resumeBuildButton.disabled = true;
  resumeBuildButton.textContent = "Resuming…";
  try {
    update(await post("/api/project/resume", {}));
  } catch (error) {
    addSystemMessage(error.message);
  } finally {
    resumeBuildButton.disabled = false;
    resumeBuildButton.textContent = "Resume build";
  }
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
  document.getElementById("archify-message").textContent = "";
  try {
    if (!state.contract || !state.plan) {
      state.contract = JSON.parse((await getJson("/api/project/file/contract.json")).content);
      state.plan = await getJson("/api/project/plan");
    }
    archifyDialog.showModal();
    renderArchify(document.getElementById("architecture-archify"), state.contract, state.plan);
  } catch (error) {
    document.getElementById("archify-message").textContent = "Diagrams could not be opened: " + error.message;
  }
}

/** Load current project state when the page opens or refreshes. */
async function initialize() {
  await Promise.all([loadSettings(), loadSkillMetadata()]);
  try {
    update(await getJson("/api/project/status"));
  } catch (error) {
    update({});
    document.getElementById("viewer-message").textContent = error.message;
  }
  connectStatus();
}

/** Clear only generated app state after the user confirms the local demo reset. */
async function prepareDemo() {
  demoButton.disabled = true;
  demoButton.textContent = "Preparing…";
  demoMessage.textContent = "Clearing generated projects and search logs…";
  try {
    const response = await fetch("/api/demo/reset", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Demo could not be prepared.");
    clearSystemMessages();
    setActiveSkills([]);
    await loadSettings();
    state.contract = null;
    state.plan = null;
    if (approval.open) approval.close();
    update({});
    resetViewer();
    setSampleIdea(sampleIdea);
    document.getElementById("demo-banner").hidden = false;
    demoDialog.close();
  } catch (error) {
    demoMessage.textContent = error.message;
  } finally {
    demoButton.disabled = false;
    demoButton.textContent = "Clear and prepare demo";
  }
}

document.getElementById("close-approval").addEventListener("click", () => approval.close());
retryApprovalButton.addEventListener("click", () => showApproval());
document.getElementById("review-plan").addEventListener("click", () => showApproval());
editButton.addEventListener("click", editContract);
approveButton.addEventListener("click", approveBuild);
document.getElementById("open-archify").addEventListener("click", openArchitecture);
document.getElementById("close-archify").addEventListener("click", () => archifyDialog.close());
document.getElementById("open-settings").addEventListener("click", openSettings);
document.getElementById("demo-mode").addEventListener("click", () => demoDialog.showModal());
document.getElementById("close-demo").addEventListener("click", () => demoDialog.close());
demoButton.addEventListener("click", prepareDemo);
resumeBuildButton.addEventListener("click", resumeBuild);
newProjectButton.addEventListener("click", () => {
  newProjectMessage.textContent = "";
  newProjectIdea.value = "";
  newProjectDialog.showModal();
  newProjectIdea.focus();
});
document.getElementById("close-new-project").addEventListener("click", () => newProjectDialog.close());
newProjectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const idea = newProjectIdea.value.trim();
  if (idea.length < 3) return;
  submitNewProjectButton.disabled = true;
  newProjectButton.disabled = true;
  submitNewProjectButton.textContent = "Starting…";
  newProjectMessage.textContent = "Starting your project…";
  try {
    await startProject(idea);
    newProjectDialog.close();
  } catch (error) {
    newProjectMessage.textContent = error.message;
    newProjectButton.disabled = false;
  } finally {
    submitNewProjectButton.disabled = false;
    submitNewProjectButton.textContent = "Start project →";
  }
});
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
document.addEventListener("skills-active", (event) => {
  setActiveSkills(event.detail.skills);
  (event.detail.skills || []).forEach((name) => addSystemMessage("Activated skill: " + name));
});
document.addEventListener("details-generated", () => {
  addSystemMessage("Project Details folder created. Open the Project Details tab.");
  loadFiles();
});
document.addEventListener("chat-message", (event) => {
  if (event.detail.message?.startsWith("Project Details could not be generated:")) {
    addSystemMessage(event.detail.message);
  }
});
initialize();
