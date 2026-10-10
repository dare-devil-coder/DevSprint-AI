/** Active skill badges derived from backend metadata and live events. */
const strip = document.getElementById("active-skills");
const metadata = new Map();
let active = [];

/** Render badges with native title descriptions and accessible names. */
function render() {
  strip.replaceChildren();
  if (!active.length) {
    const empty = document.createElement("span");
    empty.className = "skills-strip__empty";
    empty.textContent = "Skills appear as agents work.";
    strip.append(empty);
    return;
  }
  active.forEach((name) => {
    const item = metadata.get(name);
    const badge = document.createElement("button");
    badge.type = "button";
    badge.className = "skills-strip__pill";
    const label = document.createElement("span");
    label.textContent = name.replaceAll("_", " ");
    const description = document.createElement("span");
    description.className = "skills-strip__description";
    description.textContent = item?.description || "Active skill";
    description.hidden = true;
    badge.append(label, description);
    badge.title = item?.description || name;
    badge.setAttribute("aria-expanded", "false");
    badge.addEventListener("click", () => {
      badge.classList.toggle("skills-strip__pill--expanded");
      const expanded = badge.classList.contains("skills-strip__pill--expanded");
      description.hidden = !expanded;
      badge.setAttribute("aria-expanded", String(expanded));
    });
    strip.append(badge);
  });
}

/** Load only cheap skill metadata; no instruction bodies reach the browser. */
export async function loadSkillMetadata() {
  try {
    const response = await fetch("/api/skills");
    if (!response.ok) throw new Error("Skills are unavailable.");
    const data = await response.json();
    (data.skills || []).forEach((item) => metadata.set(item.name, item));
    render();
  } catch {
    strip.textContent = "Skills unavailable. Reload to retry.";
  }
}

/** Replace active skills with the backend's current task selection. */
export function setActiveSkills(names) {
  active = Array.isArray(names) ? names : [];
  render();
}
