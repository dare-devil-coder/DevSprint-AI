/** Present the saved verification report as an accessible layer table. */
const symbols = { pass: "✅", partial: "⚠️", fail: "❌", na: "—" };

/** Build a status badge with explicit text as well as an icon. */
function badge(status) {
  const span = document.createElement("span");
  span.className = "verification__badge verification__badge--" + status;
  span.textContent = (symbols[status] || "—") + " " + status;
  return span;
}

/** Render the per-layer results, summary, and actionable gaps. */
export function renderVerification(container, report) {
  container.replaceChildren();
  if (!report.layers?.length) {
    container.textContent = "Verification will appear after the first successful execution.";
    return;
  }
  const verified = report.layers.filter((layer) => layer.status === "pass").length;
  const partial = report.layers.filter((layer) => layer.status === "partial").length;
  const summary = document.createElement("p");
  summary.className = "verification__summary";
  summary.textContent = verified + " of " + report.layers.length +
    " layers verified, " + partial + " partial.";
  const table = document.createElement("table");
  table.className = "verification__table";
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  ["Layer", "Status", "Details"].forEach((title) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = title;
    row.append(cell);
  });
  head.append(row);
  const body = document.createElement("tbody");
  report.layers.forEach((layer) => {
    const entry = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = layer.name;
    const status = document.createElement("td");
    status.append(badge(layer.status));
    const details = document.createElement("td");
    details.textContent = layer.details;
    entry.append(name, status, details);
    body.append(entry);
  });
  table.append(head, body);
  container.append(summary, table);
  const title = document.createElement("h3");
  title.textContent = "Acceptance criteria";
  title.className = "verification__heading";
  container.append(title);
  const features = document.createElement("ul");
  features.className = "verification__features";
  (report.features || []).forEach((feature) => {
    const item = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = feature.feature;
    const evidence = document.createElement("p");
    evidence.textContent = feature.evidence;
    item.append(badge(feature.status), strong, evidence);
    features.append(item);
  });
  container.append(features);
  if (report.gaps?.length) {
    const gapTitle = document.createElement("h3");
    gapTitle.className = "verification__heading";
    gapTitle.textContent = "Gaps to review";
    const list = document.createElement("ul");
    list.className = "verification__gaps";
    report.gaps.forEach((gap) => {
      const item = document.createElement("li");
      item.textContent = gap.feature + ": " + gap.reason;
      list.append(item);
    });
    container.append(gapTitle, list);
  }
}
