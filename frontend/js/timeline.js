/** Full agent sequence, approval pause, and retry timeline presentation. */
export const QUESTIONS = [
  "Describe what you want to build in your own words.",
  "What should the tool take as input?",
  "What should the tool output?",
  "Any edge cases to handle (empty input, invalid input)?",
];

const steps = [
  { name: "Requirements", description: "Clarify the project contract", icon: "?" },
  { name: "Architecture", description: "Plan files and criteria", icon: "◇" },
  { name: "Approval", description: "Review contract and plan", icon: "○" },
  { name: "Coder", description: "Write Python source", icon: "</>" },
  { name: "Test Writer", description: "Write acceptance tests", icon: "✓" },
  { name: "Executor", description: "Run the code and tests", icon: "▶" },
  { name: "Self-Healing", description: "Research and apply a fix", icon: "↻" },
  { name: "Verifier", description: "Check each requirement", icon: "◎" },
  { name: "Doc Agent", description: "Write project README", icon: "≡" },
];
const states = new Map();

/** Paint the stable four-step sequence and any active retry. */
export function renderTimeline(project = {}) {
  const list = document.getElementById("agent-timeline");
  const active = project.agent || "";
  const phase = project.phase || "";
  if (phase === "questions" && !project.answers?.length) states.clear();
  const items = steps.map((step) => {
    let status = project.completed_agents?.includes(step.name) ? "done" :
      states.get(step.name) || "idle";
    if (phase === "questions" && step.name === "Requirements") status = "working";
    if ((phase === "building" || phase === "planning") && step.name === active) status = "working";
    if (step.name === "Approval") {
      status = phase === "awaiting_approval" ? "working" : project.approved ? "done" : "idle";
    }
    if (phase === "error" && step.name === active) status = "error";
    return { ...step, status };
  });
  list.replaceChildren();
  items.forEach((step) => {
    const item = document.createElement("li");
    item.className = "timeline__item timeline__item--" + step.status;
    const node = document.createElement("span");
    node.className = "timeline__node";
    node.setAttribute("aria-hidden", "true");
    node.textContent = step.status === "done" ? "✓" : step.status === "error" ? "×" : step.icon;
    const text = document.createElement("span");
    const name = document.createElement("span");
    name.className = "timeline__name";
    name.textContent = step.name;
    const description = document.createElement("span");
    description.className = "timeline__description";
    description.textContent = step.description;
    text.append(name, description);
    const status = document.createElement("span");
    status.className = "timeline__state";
    status.textContent = step.name === "Approval" && phase === "awaiting_approval" ?
      "waiting" : step.status;
    item.append(node, text, status);
    list.append(item);
  });
  document.getElementById("phase-copy").textContent = project.message || "Waiting for your idea";
  document.getElementById("attempt-copy").textContent = project.verification_retry ?
    "REVISION " + project.verification_retry + "/3" :
    project.attempt ? "RUN " + project.attempt : "";
  document.getElementById("open-archify").disabled = !project.completed_agents?.includes("Architecture");
  const pill = document.getElementById("header-status");
  pill.className = "status-pill" + (["building", "planning", "questions"].includes(phase) ? " status-pill--working" : "") +
    (phase === "error" ? " status-pill--error" : "");
  pill.lastElementChild.textContent = phase === "complete" ? "Build complete" :
    phase === "error" ? "Needs attention" : phase === "awaiting_approval" ?
    "Approval needed" : active ? active + " working" : "Ready to build";
}

/** Update one agent from a WebSocket lifecycle event. */
export function setAgentStatus(detail, project) {
  states.set(detail.agent, detail.status);
  renderTimeline(project);
}
