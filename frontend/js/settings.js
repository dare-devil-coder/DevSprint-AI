/** Settings dialog and durable learner preferences. */
const dialog = document.getElementById("settings-dialog");
const form = document.getElementById("settings-form");
const details = document.getElementById("generate-details");
const level = document.getElementById("skill-level");
const message = document.getElementById("settings-message");
const save = document.getElementById("save-settings");
const storageKey = "devsprint-settings";

/** Read server settings and mirror them locally for refresh and offline display. */
export async function loadSettings() {
  message.textContent = "Loading settings…";
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) throw new Error("Settings could not be loaded.");
    const settings = await response.json();
    details.checked = Boolean(settings.generate_project_details);
    level.value = settings.skill_level || "beginner";
    localStorage.setItem(storageKey, JSON.stringify(settings));
    message.textContent = "";
  } catch (error) {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (saved) {
        details.checked = Boolean(saved.generate_project_details);
        level.value = saved.skill_level || "beginner";
      }
    } catch {
      localStorage.removeItem(storageKey);
    }
    message.textContent = error.message;
  }
}

/** Open settings with the latest saved values. */
export function openSettings() {
  if (!dialog.open) dialog.showModal();
}

/** Save the current values to the backend and local storage. */
async function saveSettings(event) {
  event.preventDefault();
  save.disabled = true;
  save.textContent = "Saving…";
  message.textContent = "Saving settings…";
  const settings = {
    generate_project_details: details.checked,
    skill_level: level.value,
  };
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Settings could not be saved.");
    localStorage.setItem(storageKey, JSON.stringify(data));
    message.textContent = "Settings saved.";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    save.disabled = false;
    save.textContent = "Save settings";
  }
}

form.addEventListener("submit", saveSettings);
document.getElementById("close-settings").addEventListener("click", () => dialog.close());
