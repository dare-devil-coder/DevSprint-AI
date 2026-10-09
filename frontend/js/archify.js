/** Mermaid diagrams derived only from the saved contract and architecture plan. */
let mermaidPromise;

/** Keep user-authored labels safe within a Mermaid quoted node. */
function label(value) {
  return String(value).replace(/["<>\[\]{}|]/g, "").replace(/\s+/g, " ").trim().slice(0, 90) || "Unnamed";
}

/** Build source text for the user workflow from contract inputs and outputs. */
function workflow(contract) {
  const lines = ["flowchart LR"];
  const inputs = contract.inputs?.length ? contract.inputs : ["Input"];
  const outputs = contract.outputs?.length ? contract.outputs : ["Output"];
  inputs.forEach((item, index) => lines.push('i' + index + '["' + label(item) + '"] --> process'));
  lines.push('process["' + label(contract.description) + '"]');
  outputs.forEach((item, index) => lines.push('process --> o' + index + '["' + label(item) + '"]'));
  return lines.join("\n");
}

/** Build file dependency edges from the plan's declared structure. */
function architecture(plan) {
  const files = plan.file_structure || [];
  const ids = new Map(files.map((file, index) => [file.path, "f" + index]));
  const lines = ["flowchart LR"];
  files.forEach((file, index) => {
    lines.push('f' + index + '["' + label(file.path) + '"]');
    (file.depends_on || []).forEach((dependency) => {
      if (ids.has(dependency)) lines.push(ids.get(dependency) + " --> f" + index);
    });
  });
  return lines.join("\n");
}

/** Build a data path using only named inputs, files, and outputs. */
function dataFlow(contract, plan) {
  const order = plan.build_order || [];
  const lines = ["flowchart LR", 'source["' + label((contract.inputs || []).join(", ")) + '"]'];
  order.forEach((file, index) => {
    lines.push('m' + index + '["' + label(file) + '"]');
    lines.push((index ? "m" + (index - 1) : "source") + " --> m" + index);
  });
  lines.push('result["' + label((contract.outputs || []).join(", ")) + '"]');
  lines.push((order.length ? "m" + (order.length - 1) : "source") + " --> result");
  return lines.join("\n");
}

/** Import Mermaid once from the only permitted external JavaScript library. */
async function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("https://cdn.jsdelivr.net/npm/mermaid@12/dist/mermaid.esm.min.mjs");
  }
  const module = await mermaidPromise;
  module.default.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
  return module.default;
}

/** Present a readable data-derived diagram when the CDN is unavailable. */
function fallback(container, title, source) {
  container.replaceChildren();
  const heading = document.createElement("p");
  heading.className = "archify__fallback-label";
  heading.textContent = title + " · diagram source";
  const code = document.createElement("pre");
  code.className = "archify__fallback-source";
  code.textContent = source;
  container.append(heading, code);
}

/** Render three switchable Mermaid diagrams from contract and plan data. */
export function renderArchify(container, contract, plan) {
  const diagrams = [
    { title: "User workflow", source: workflow(contract) },
    { title: "System architecture", source: architecture(plan) },
    { title: "Data flow", source: dataFlow(contract, plan) },
  ];
  container.replaceChildren();
  const tabs = document.createElement("div");
  tabs.className = "archify__tabs";
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Architecture diagrams");
  const surface = document.createElement("div");
  surface.className = "archify__surface";
  container.append(tabs, surface);
  let active = 0;
  /** Select and render one diagram, retaining the source as a fallback. */
  async function show(index) {
    active = index;
    [...tabs.children].forEach((button, position) =>
      button.setAttribute("aria-selected", String(position === active)));
    surface.replaceChildren();
    const loading = document.createElement("p");
    loading.className = "archify__loading";
    loading.textContent = "Rendering diagram…";
    surface.append(loading);
    try {
      const mermaid = await getMermaid();
      if (active !== index || !container.isConnected) return;
      const pre = document.createElement("pre");
      pre.className = "mermaid";
      pre.textContent = diagrams[index].source;
      surface.replaceChildren(pre);
      await mermaid.run({ nodes: [pre] });
    } catch {
      if (active === index) fallback(surface, diagrams[index].title, diagrams[index].source);
    }
  }
  diagrams.forEach((diagram, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "archify__tab";
    button.role = "tab";
    button.textContent = diagram.title;
    button.addEventListener("click", () => show(index));
    tabs.append(button);
  });
  show(0);
}
