/** Chat rendering and accessible project idea and answer forms. */
import { QUESTIONS } from "./timeline.js";

const history = document.getElementById("chat-history");
const composer = document.getElementById("chat-composer");
const notices = [];

/** Create and append one safely escaped message using textContent. */
function addMessage(role, message) {
  const article = document.createElement("article");
  article.className = "chat__message chat__message--" + role;
  const sender = document.createElement("span");
  sender.className = "chat__sender";
  sender.textContent = role === "user" ? "You" : "DevSprint AI";
  const bubble = document.createElement("p");
  bubble.className = "chat__bubble";
  bubble.textContent = message;
  article.append(sender, bubble);
  history.append(article);
  history.scrollTop = history.scrollHeight;
}

/** Rebuild the chat from durable project state, including the current question. */
export function renderChat(state, onStart, onAnswer) {
  history.replaceChildren();
  composer.replaceChildren();
  if (!state.idea) {
    const welcome = document.createElement("div");
    welcome.className = "chat__welcome";
    const heading = document.createElement("h2");
    heading.textContent = "A working project starts here.";
    const copy = document.createElement("p");
    copy.textContent = "Describe a product, website, or tool. We’ll clarify the important details, build a working prototype, and verify it against your requirements.";
    welcome.append(heading, copy);
    history.append(welcome);
    renderForm("idea", onStart);
    return;
  }
  addMessage("user", state.idea);
  state.answers.forEach((answer, index) => {
    addMessage("agent", state.questions?.[index] || QUESTIONS[index]);
    addMessage("user", answer);
  });
  notices.forEach((notice) => addMessage("agent", notice));
  if (state.phase === "questions") {
    addMessage("agent", state.question);
    renderForm("answer", onAnswer);
  } else {
    if (state.phase === "awaiting_approval") {
      addMessage("agent", "Contract and architecture ready. Review and approve to start building.");
    }
    const notice = document.createElement("p");
    notice.className = "chat__notice";
    notice.textContent = state.phase === "complete" ? "Project ready. Explore the generated files." :
      state.phase === "error" ? state.message :
      state.phase === "awaiting_approval" ? "Building is paused for your approval." :
      state.phase === "planning" ? "Preparing the contract and plan…" :
      "The agents are building your project…";
    composer.append(notice);
  }
}

/** Add an in-session update for skill activation or explanation generation. */
export function addSystemMessage(message) {
  if (!notices.includes(message)) notices.push(message);
  addMessage("agent", message);
}

/** Reset transient notices when a new project or clean demo starts. */
export function clearSystemMessages() {
  notices.length = 0;
}

/** Prefill the existing idea composer without submitting it. */
export function setSampleIdea(idea) {
  const input = composer.querySelector("textarea");
  if (input) {
    input.value = idea;
    input.focus();
  }
}

/** Render a labeled textarea with Enter-to-send and a visible busy state. */
function renderForm(mode, submit) {
  const form = document.createElement("form");
  form.className = "chat__form" + (mode === "answer" ? " chat__form--answer" : "");
  const label = document.createElement("label");
  label.className = "chat__label";
  label.textContent = mode === "idea" ? "YOUR PROJECT IDEA" : "YOUR ANSWER";
  const input = document.createElement("textarea");
  input.className = "chat__input";
  input.required = true;
  input.maxLength = 4000;
  input.placeholder = mode === "idea" ? "Build a reading tracker website with a calm editorial style…" : "Type your answer here…";
  label.append(input);
  const actions = document.createElement("div");
  actions.className = "chat__actions";
  const hint = document.createElement("span");
  hint.className = "chat__hint";
  hint.textContent = "Enter to send · Shift+Enter for a new line";
  const button = document.createElement("button");
  button.className = "button";
  button.type = "submit";
  button.textContent = mode === "idea" ? "Start project →" : "Send answer →";
  actions.append(hint, button);
  const error = document.createElement("p");
  error.className = "chat__error";
  error.setAttribute("role", "alert");
  form.append(label, actions, error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    button.disabled = true;
    input.disabled = true;
    button.textContent = mode === "idea" ? "Starting…" : "Sending…";
    error.textContent = "";
    try {
      await submit(value);
    } catch (problem) {
      error.textContent = problem.message;
      button.disabled = false;
      input.disabled = false;
      button.textContent = mode === "idea" ? "Start project →" : "Send answer →";
    }
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  composer.append(form);
}
