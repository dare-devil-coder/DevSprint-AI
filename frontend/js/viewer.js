/** Project contract, code, output, and SerpApi audit log viewer. */
import { renderVerification } from "./verification.js";

const tabs = document.getElementById("viewer-tabs");
const content = document.getElementById("viewer-content");
const verification = document.getElementById("viewer-verification");
const details = document.getElementById("viewer-details");
const preview = document.getElementById("viewer-preview");
const caption = document.getElementById("viewer-caption");
const message = document.getElementById("viewer-message");
let filePaths = [];
let selected = "contract.json";
let selectedDepth = "";
const previewStoragePrefix = "__devsprint_preview__:";

// Sandboxed previews have an opaque origin. Bridge only their storage messages,
// scoped to this iframe and its generated project name.
window.addEventListener("message", (event) => {
  if (event.source !== preview.contentWindow) return;
  const data = event.data;
  const project = preview.dataset.projectName;
  if (!project || !data || data.project !== project) return;
  const prefix = previewStoragePrefix + project + ":";
  try {
    if (data.type === "devsprint-preview-storage-ready") {
      const entries = [];
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key?.startsWith(prefix)) entries.push([key.slice(prefix.length), localStorage.getItem(key)]);
      }
      preview.contentWindow.postMessage({ type: "devsprint-preview-storage-init", project, entries }, "*");
    } else if (data.type === "devsprint-preview-storage-set" && typeof data.key === "string" && typeof data.value === "string") {
      localStorage.setItem(prefix + data.key.slice(0, 500), data.value.slice(0, 1_000_000));
    } else if (data.type === "devsprint-preview-storage-remove" && typeof data.key === "string") {
      localStorage.removeItem(prefix + data.key.slice(0, 500));
    } else if (data.type === "devsprint-preview-storage-clear") {
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index);
        if (key?.startsWith(prefix)) localStorage.removeItem(key);
      }
    }
  } catch {
    // Keep the prototype usable in private browsing modes that disable storage.
  }
});

preview.addEventListener("load", () => {
  if (selected === "Preview" && preview.src) caption.textContent = "Preview ready";
});
preview.addEventListener("error", () => {
  caption.textContent = "Preview unavailable";
  message.textContent = "The prototype preview could not be loaded. Try refreshing the project.";
});

/** Fetch JSON and surface HTTP errors as user-facing text. */
async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Could not load " + path + ".");
  return response.json();
}

/** Refresh available files and keep the current tab when possible. */
export async function loadFiles() {
  message.textContent = "Loading project files…";
  try {
    const data = await getJson("/api/project/files");
    filePaths = data.files;
    if (!filePaths.includes(selected) && !["Output", "SerpApi Log", "Verification", "Project Details"].includes(selected)) {
      selected = filePaths[0] || "Output";
    }
    renderTabs();
    await loadFile(selected);
  } catch (error) {
    message.textContent = error.message;
  }
}

/** Render file and result tabs with keyboard-accessible native buttons. */
function renderTabs() {
  tabs.replaceChildren();
  const paths = [...filePaths, "Output", "Verification", "SerpApi Log", "Project Details"];
  paths.forEach((path, index) => {
    const button = document.createElement("button");
    button.className = "viewer__tab";
    button.type = "button";
    button.role = "tab";
    button.id = "viewer-tab-" + index;
    button.setAttribute("aria-controls", "viewer-content-area");
    button.tabIndex = selected === path ? 0 : -1;
    button.dataset.path = path;
    button.textContent = path.includes("/") ? path.split("/").pop() : path;
    button.setAttribute("aria-selected", String(selected === path));
    button.addEventListener("click", () => activateTab(path));
    button.addEventListener("keydown", (event) => {
      const next = event.key === "ArrowRight" ? (index + 1) % paths.length :
        event.key === "ArrowLeft" ? (index - 1 + paths.length) % paths.length :
        event.key === "Home" ? 0 : event.key === "End" ? paths.length - 1 : -1;
      if (next < 0) return;
      event.preventDefault();
      activateTab(paths[next]);
    });
    tabs.append(button);
  });
  document.getElementById("viewer-content-area").setAttribute("aria-labelledby", "viewer-tab-" + paths.indexOf(selected));
}

/** Select a tab and return keyboard focus to its replacement button. */
async function activateTab(path) {
  await loadFile(path);
  [...tabs.children].find((button) => button.dataset.path === path)?.focus();
}

/** Show cached explanation levels and generate the next level on request. */
async function renderDetails() {
  details.replaceChildren();
  const status = document.createElement("p");
  status.className = "viewer__details-status";
  status.textContent = "Loading Project Details…";
  details.append(status);
  try {
    const data = await getJson("/api/project/details");
    const files = data.files || [];
    if (!files.length) {
      status.textContent = "No explanations yet. Turn on Project Details in Settings before approving a build.";
      return;
    }
    selectedDepth = files.includes(selectedDepth) ? selectedDepth : files[0];
    details.replaceChildren();
    const levels = document.createElement("div");
    levels.className = "viewer__depth-tabs";
    files.forEach((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "viewer__depth-tab";
      button.textContent = "Level " + (name.match(/level_(\d)/)?.[1] || name);
      button.setAttribute("aria-pressed", String(name === selectedDepth));
      button.addEventListener("click", () => {
        selectedDepth = name;
        renderDetails();
      });
      levels.append(button);
    });
    const explanation = document.createElement("pre");
    explanation.className = "viewer__details-content";
    explanation.textContent = "Loading explanation…";
    details.append(levels, explanation);
    const response = await getJson("/api/project/details/" + encodeURIComponent(selectedDepth));
    explanation.textContent = response.content;
    const next = [3, 4].find((value) => !files.some((name) => name.startsWith("level_" + value + "_")));
    if (next) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button--secondary viewer__deeper";
      button.textContent = next === 3 ? "Explain deeper · Level 3" : "Explain deeper · Level 4";
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Generating explanation…";
        try {
          const result = await fetch("/api/project/details/deeper", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ level: next }),
          });
          const body = await result.json();
          if (!result.ok) throw new Error(body.detail || "Could not generate this level.");
          selectedDepth = (body.files || []).find((name) => name.startsWith("level_" + next + "_")) || "";
          await renderDetails();
        } catch (error) {
          button.disabled = false;
          button.textContent = "Try Level " + next + " again";
          message.textContent = error.message;
        }
      });
      details.append(button);
    }
  } catch (error) {
    status.textContent = "Project Details could not be loaded.";
    message.textContent = error.message;
  }
}

/** Load and pretty-print the chosen source file or run artifact. */
export async function loadFile(path) {
  selected = path;
  renderTabs();
  caption.textContent = path;
  content.textContent = "Loading…";
  content.hidden = path === "Verification" || path === "Preview";
  preview.hidden = path !== "Preview";
  verification.hidden = path !== "Verification";
  details.hidden = path !== "Project Details";
  if (path === "Project Details") content.hidden = true;
  if (path === "Verification") verification.textContent = "Loading verification…";
  message.textContent = "";
  try {
    if (path === "Preview") {
      preview.title = "Generated project preview";
      caption.textContent = "Loading preview…";
      const contractResponse = await fetch("/api/project/file/contract.json");
      const contractFile = await contractResponse.json();
      if (!contractResponse.ok) throw new Error(contractFile.detail || "Project contract is not available.");
      const projectName = JSON.parse(contractFile.content).project_name;
      if (typeof projectName !== "string" || !projectName) throw new Error("The project name is missing from its contract.");
      preview.dataset.projectName = projectName;
      const response = await fetch("/api/project/preview?refresh=" + Date.now());
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "The generated preview is not ready yet.");
      }
      if (selected === "Preview") {
        preview.src = "/api/project/preview?refresh=" + Date.now();
        content.textContent = "Interactive prototype preview";
        caption.textContent = "Opening preview…";
      }
    } else if (path === "Project Details") {
      await renderDetails();
    } else if (path === "Verification") {
      renderVerification(verification, await getJson("/api/project/verification"));
    } else if (path === "Output") {
      const data = await getJson("/api/project/output");
      content.textContent = Object.keys(data).length ?
        (data.success ? "✓ Execution passed" : "× Execution failed") +
        "\n\n" + (data.output || "No stdout.") + (data.error ? "\n\nERROR\n" + data.error : "") :
        "Execution results will appear after the first run.";
    } else if (path === "SerpApi Log") {
      const data = await getJson("/api/project/serpapi-log");
      content.textContent = data.calls?.length ? JSON.stringify(data, null, 2) :
        "No search yet. SerpApi runs when generated code needs a repair.";
    } else {
      const data = await getJson("/api/project/file/" + encodeURI(path));
      content.textContent = path.endsWith(".json") ? JSON.stringify(JSON.parse(data.content), null, 2) : data.content;
    }
  } catch (error) {
    if (path === "Preview") caption.textContent = "Preview unavailable";
    if (path === "Verification") verification.textContent = "Could not load verification.";
    else content.textContent = "Could not load this item.";
    message.textContent = error.message;
  }
}

/** Clear selected viewer state when a clean demo starts. */
export function resetViewer() {
  filePaths = [];
  selected = "Output";
  selectedDepth = "";
  renderTabs();
  loadFile("Output");
}
