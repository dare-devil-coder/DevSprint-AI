/** Project contract, code, output, and SerpApi audit log viewer. */
import { renderVerification } from "./verification.js";

const tabs = document.getElementById("viewer-tabs");
const content = document.getElementById("viewer-content");
const verification = document.getElementById("viewer-verification");
const caption = document.getElementById("viewer-caption");
const message = document.getElementById("viewer-message");
let filePaths = [];
let selected = "contract.json";

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
    if (!filePaths.includes(selected) && !["Output", "SerpApi Log", "Verification"].includes(selected)) {
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
  [...filePaths, "Output", "Verification", "SerpApi Log"].forEach((path) => {
    const button = document.createElement("button");
    button.className = "viewer__tab";
    button.type = "button";
    button.role = "tab";
    button.textContent = path.includes("/") ? path.split("/").pop() : path;
    button.setAttribute("aria-selected", String(selected === path));
    button.addEventListener("click", () => loadFile(path));
    tabs.append(button);
  });
}

/** Load and pretty-print the chosen source file or run artifact. */
export async function loadFile(path) {
  selected = path;
  renderTabs();
  caption.textContent = path;
  content.textContent = "Loading…";
  content.hidden = path === "Verification";
  verification.hidden = path !== "Verification";
  if (path === "Verification") verification.textContent = "Loading verification…";
  message.textContent = "";
  try {
    if (path === "Verification") {
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
    if (path === "Verification") verification.textContent = "Could not load verification.";
    else content.textContent = "Could not load this item.";
    message.textContent = error.message;
  }
}
