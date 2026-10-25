const state = { panel: [], cases: [], activeCaseId: null };

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

async function loadPanel() {
  state.panel = await api("/api/panel");
  const select = document.getElementById("patient-select");
  select.innerHTML = state.panel
    .map((p) => `<option value="${p.id}">${p.name} (DOB ${p.dob})</option>`)
    .join("");
}

async function loadCases() {
  state.cases = await api("/api/cases");
  const list = document.getElementById("case-list");
  if (state.cases.length === 0) {
    list.innerHTML = '<li class="muted">No cases yet.</li>';
    return;
  }
  list.innerHTML = state.cases
    .map(
      (c) => `
      <li data-id="${c.id}" class="${c.id === state.activeCaseId ? "active" : ""}">
        ${c.patient_name} &mdash; ${c.reason}
        <span class="status-badge">${c.status}</span>
      </li>`
    )
    .join("");
  list.querySelectorAll("li[data-id]").forEach((li) => {
    li.addEventListener("click", () => openCase(li.dataset.id));
  });
}

function roundsBlock(rounds) {
  return (rounds || [])
    .map((r) => {
      const failures = r.failures || [];
      return `
      <details ${r.passed ? "" : "open"}>
        <summary>Round ${r.round}: ${r.passed ? "passed" : "failed"} (${failures.length} issue${failures.length === 1 ? "" : "s"})</summary>
        ${
          failures.length
            ? `<ul>${failures
                .map((f) => `<li><strong>${escapeHtml(f.sentence)}</strong> &mdash; ${escapeHtml(f.reason)}</li>`)
                .join("")}</ul>`
            : ""
        }
        <pre>${escapeHtml(r.draft)}</pre>
      </details>`;
    })
    .join("");
}

function stepBlock(caseId, step, index) {
  const approved =
    step.approved === true
      ? '<span class="approved-yes">approved</span>'
      : step.approved === false
      ? '<span class="approved-no">rejected</span>'
      : '<span class="muted">not reviewed</span>';
  const rounds = step.verification_rounds || [];
  const resolvedBadge = step.resolved
    ? `<span class="approved-yes">verifier passed (round ${rounds.length})</span>`
    : '<span class="approved-no">verifier did NOT pass after 3 rounds &mdash; needs manual review</span>';
  return `
    <div class="step">
      <h3>${step.agent} <small>${step.model} / thinking: ${step.thinking_level}</small></h3>
      <p>${resolvedBadge}</p>
      <pre>${escapeHtml(step.output)}</pre>
      <details>
        <summary>Verification log (${rounds.length} round${rounds.length === 1 ? "" : "s"})</summary>
        ${roundsBlock(rounds)}
      </details>
      <div class="review-row">
        ${approved}
        <button class="ok" style="width:auto" onclick="reviewStep('${caseId}', ${index}, true)">Approve</button>
        <button class="bad" style="width:auto" onclick="reviewStep('${caseId}', ${index}, false)">Reject</button>
      </div>
    </div>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

async function openCase(caseId) {
  state.activeCaseId = caseId;
  await loadCases();
  const c = await api(`/api/cases/${caseId}`);
  const detail = document.getElementById("case-detail");
  const reviewBanner = c.needs_manual_review
    ? '<p class="approved-no">One or more steps never passed verification after 3 rounds &mdash; review those steps before acting on this case.</p>'
    : "";
  detail.innerHTML = `
    <h2>Case detail</h2>
    <p><strong>${c.patient.name}</strong> &mdash; ${c.reason} <span class="status-badge">${c.status}</span></p>
    <p class="muted">Raw notes: ${escapeHtml(c.notes)}</p>
    ${reviewBanner}
    <button id="run-pipeline-btn">Run back-office pipeline</button>
    <div id="steps">${c.steps.map((s, i) => stepBlock(c.id, s, i)).join("") || '<p class="muted">No steps run yet.</p>'}</div>
  `;
  document.getElementById("run-pipeline-btn").addEventListener("click", () => runPipeline(caseId));
}

async function runPipeline(caseId) {
  const btn = document.getElementById("run-pipeline-btn");
  btn.disabled = true;
  btn.textContent = "Running agents... (can take a few minutes)";
  try {
    await api(`/api/cases/${caseId}/run`, { method: "POST" });
    await openCase(caseId);
  } catch (e) {
    alert("Pipeline failed: " + e.message);
    btn.disabled = false;
    btn.textContent = "Run back-office pipeline";
  }
}

async function reviewStep(caseId, index, approved) {
  await api(`/api/cases/${caseId}/steps/${index}/review`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
  await openCase(caseId);
}

document.getElementById("create-case-btn").addEventListener("click", async () => {
  const patient_id = document.getElementById("patient-select").value;
  const reason = document.getElementById("reason-input").value.trim();
  const notes = document.getElementById("notes-input").value.trim();
  if (!patient_id || !reason) {
    alert("Pick a patient and enter a reason for visit.");
    return;
  }
  const c = await api("/api/cases", {
    method: "POST",
    body: JSON.stringify({ patient_id, reason, notes }),
  });
  document.getElementById("reason-input").value = "";
  document.getElementById("notes-input").value = "";
  await loadCases();
  await openCase(c.id);
});

document.getElementById("agent-builder-btn").addEventListener("click", async () => {
  const description = document.getElementById("agent-builder-input").value.trim();
  if (!description) return;
  const out = document.getElementById("agent-builder-output");
  out.style.display = "block";
  out.textContent =
    "Spinning up a real Antigravity sandbox with gemini-4-argon to write and test this... can take a minute or two, uses real API usage.";
  try {
    const res = await api("/api/agent-builder", {
      method: "POST",
      body: JSON.stringify({ description }),
    });
    out.textContent = `[status: ${res.status}] environment: ${res.environment_id}\n\n${res.output}`;
  } catch (e) {
    out.textContent = "Failed: " + e.message;
  }
});

document.getElementById("test-argon-btn").addEventListener("click", async () => {
  const span = document.getElementById("test-argon-result");
  span.textContent = "asking gemini-4-argon...";
  try {
    const res = await api("/test-argon");
    span.textContent = `${res.model} says: "${res.output}"`;
  } catch (e) {
    span.textContent = "failed: " + e.message;
  }
});

loadPanel();
loadCases();
