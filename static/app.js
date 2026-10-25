const state = { currentTab: "visits", activeVisitId: null };

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

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function inlineMd(s) {
  let escaped = escapeHtml(s);
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  escaped = escaped.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  return escaped;
}

// Small hand-rolled renderer for the subset of markdown the agents produce
// (headers as **bold** or #, bullet/numbered lists, --- rules). Not a full
// markdown parser - just enough to stop showing raw ** to the physician.
function renderMarkdown(text) {
  if (!text) return "";
  const lines = text.split("\n");
  let html = "";
  let listType = null;

  function closeList() {
    if (listType) {
      html += `</${listType}>`;
      listType = null;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      closeList();
      html += "<hr>";
      continue;
    }
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    const boldHeadingMatch = !headingMatch && line.match(/^\*\*(.+?)\*\*:?\s*$/);
    const bulletMatch = line.match(/^\s*[*-]\s+(.*)$/);
    const numberedMatch = line.match(/^\s*\d+\.\s+(.*)$/);

    if (headingMatch) {
      closeList();
      const level = Math.min(headingMatch[1].length + 2, 6);
      html += `<h${level}>${inlineMd(headingMatch[2])}</h${level}>`;
    } else if (boldHeadingMatch) {
      closeList();
      html += `<h4>${inlineMd(boldHeadingMatch[1])}</h4>`;
    } else if (bulletMatch) {
      if (listType !== "ul") {
        closeList();
        html += "<ul>";
        listType = "ul";
      }
      html += `<li>${inlineMd(bulletMatch[1])}</li>`;
    } else if (numberedMatch) {
      if (listType !== "ol") {
        closeList();
        html += "<ol>";
        listType = "ol";
      }
      html += `<li>${inlineMd(numberedMatch[1])}</li>`;
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList();
      html += `<p>${inlineMd(line)}</p>`;
    }
  }
  closeList();
  return html;
}

const DOC_LABELS = {
  scribe: "Scribe note",
  prescription: "Prescription (SIMULATED FAX)",
  emails: "Patient summary email",
};

// ---------- Tab switching ----------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  render();
}

function render() {
  const map = {
    visits: renderVisits,
    approvals: renderApprovals,
    activity: renderActivity,
    "agent-builder": renderAgentBuilderPlaceholder,
    results: renderResultsPlaceholder,
    practice: renderPracticePlaceholder,
    booking: renderBookingPlaceholder,
  };
  (map[state.currentTab] || renderVisits)();
}

// ---------- Visits ----------

async function renderVisits() {
  const container = document.getElementById("tab-content");
  const visits = await api("/api/visits");
  container.innerHTML = `
    <div class="two-col">
      <section class="panel">
        <h2>Visits</h2>
        <ul class="case-list" id="visit-list">
          ${
            visits.length
              ? visits
                  .map(
                    (v) => `
              <li data-id="${v.id}" class="${v.id === state.activeVisitId ? "active" : ""}">
                ${escapeHtml(v.patient_name)} &mdash; ${escapeHtml(v.reason)}
                <span class="status-badge">${v.status}</span>
                ${v.needs_manual_review ? '<span class="approved-no">needs review</span>' : ""}
              </li>`
                  )
                  .join("")
              : '<li class="muted">No visits booked yet. Use the Booking page tab (coming soon) or POST /api/booking.</li>'
          }
        </ul>
      </section>
      <section class="panel" id="visit-detail"><p class="muted">Select a visit.</p></section>
    </div>
  `;
  container.querySelectorAll("#visit-list li[data-id]").forEach((li) => {
    li.addEventListener("click", () => openVisit(li.dataset.id));
  });
  if (state.activeVisitId) await openVisit(state.activeVisitId);
}

async function openVisit(visitId) {
  state.activeVisitId = visitId;
  const v = await api(`/api/visits/${visitId}`);
  const detail = document.getElementById("visit-detail");
  if (!detail) return;
  const patient = v.patient;
  const recordsHtml = `
    <h3>Records</h3>
    <p><strong>${escapeHtml(patient.name)}</strong> (DOB ${escapeHtml(patient.dob || "unknown")})</p>
    <p>Conditions: ${escapeHtml((patient.conditions || []).join(", ") || "none on file")}</p>
    <p>Meds: ${escapeHtml((patient.meds || []).join(", ") || "none on file")}</p>
    <p>Labs: ${escapeHtml((patient.labs || []).map((l) => `${l.date} ${l.test}: ${l.result}`).join("; ") || "none on file")}</p>
    <p>Vitals: ${escapeHtml(JSON.stringify(patient.vitals || {}))}</p>
  `;
  const canApprove = !["awaiting_approval", "completed"].includes(v.status);
  const docsHtml = Object.entries(v.documents || {})
    .map(([docType, doc]) => documentBlock(v.id, docType, doc))
    .join("");
  const reviewBanner = v.needs_manual_review
    ? '<p class="approved-no">One or more documents never passed verification after 3 rounds &mdash; review before approving.</p>'
    : "";
  detail.innerHTML = `
    <h2>Visit detail</h2>
    <p><span class="status-badge">${v.status}</span></p>
    ${reviewBanner}
    <div class="two-col">
      <div>
        <h3>Intake summary</h3>
        <div class="doc-text">${renderMarkdown(v.intake_summary) || '<p class="muted">(not generated yet)</p>'}</div>
        ${recordsHtml}
      </div>
      <div>
        <label>Transcript</label>
        <textarea id="transcript-box" rows="8">${escapeHtml(v.transcript)}</textarea>
        <label>Physician plan</label>
        <textarea id="plan-box" rows="4">${escapeHtml(v.physician_plan)}</textarea>
        <button id="save-transcript-btn">Save</button>
        <button id="approve-visit-btn" ${canApprove ? "" : "disabled"}>Approve &amp; run pipeline</button>
      </div>
    </div>
    <div id="visit-documents">${docsHtml}</div>
  `;
  document.getElementById("save-transcript-btn").addEventListener("click", async () => {
    await api(`/api/visits/${visitId}`, {
      method: "PATCH",
      body: JSON.stringify({
        transcript: document.getElementById("transcript-box").value,
        physician_plan: document.getElementById("plan-box").value,
      }),
    });
  });
  document.getElementById("approve-visit-btn").addEventListener("click", async () => {
    const btn = document.getElementById("approve-visit-btn");
    btn.disabled = true;
    btn.textContent = "Running scribe -> prescription -> email pipeline... can take a few minutes";
    await api(`/api/visits/${visitId}`, {
      method: "PATCH",
      body: JSON.stringify({
        transcript: document.getElementById("transcript-box").value,
        physician_plan: document.getElementById("plan-box").value,
      }),
    });
    try {
      await api(`/api/visits/${visitId}/approve`, { method: "POST" });
      await openVisit(visitId);
    } catch (e) {
      alert("Pipeline failed: " + e.message);
    }
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
        <div class="doc-text">${renderMarkdown(r.draft)}</div>
      </details>`;
    })
    .join("");
}

// Not collapsed - a rejected round needs to be visible without clicking
// anything, so the verifier catching an error is obvious in the demo.
function rejectedCallouts(rounds) {
  const rejected = (rounds || []).filter((r) => !r.passed);
  if (!rejected.length) return "";
  return rejected
    .map(
      (r) => `
    <div class="verifier-catch">
      <strong>Verifier rejected round ${r.round}:</strong>
      <ul>
        ${(r.failures || [])
          .map((f) => `<li><strong>"${escapeHtml(f.sentence)}"</strong> &mdash; ${escapeHtml(f.reason)}</li>`)
          .join("")}
      </ul>
    </div>`
    )
    .join("");
}

function documentBlock(visitId, docType, doc) {
  const rounds = doc.verification_rounds || [];
  const resolvedBadge = doc.resolved
    ? `<span class="approved-yes">verifier passed (round ${rounds.length})</span>`
    : '<span class="approved-no">verifier did NOT pass after 3 rounds &mdash; needs manual review</span>';
  const approval = doc.approval || { status: "pending" };
  const canSend = approval.status === "approved" && !doc.sent;
  return `
    <div class="step">
      <h3>${DOC_LABELS[docType] || docType} <span class="status-badge">${approval.status}</span></h3>
      <p>${resolvedBadge}</p>
      ${rejectedCallouts(rounds)}
      <div class="doc-text">${renderMarkdown(doc.output)}</div>
      <details>
        <summary>Full verifier log (${rounds.length} round${rounds.length === 1 ? "" : "s"})</summary>
        ${roundsBlock(rounds)}
      </details>
      <div class="review-row">
        <button class="ok" onclick="decideDocument('${visitId}','${docType}','approved')">Approve</button>
        <button onclick="editDocument('${visitId}','${docType}')">Edit</button>
        <button class="bad" onclick="decideDocument('${visitId}','${docType}','rejected')">Reject</button>
        ${
          doc.sent
            ? '<span class="approved-yes">sent</span>'
            : `<button ${canSend ? "" : "disabled"} onclick="sendDocument('${visitId}','${docType}')">Send (simulated)</button>`
        }
      </div>
    </div>`;
}

async function decideDocument(visitId, docType, status) {
  await api(`/api/visits/${visitId}/documents/${docType}/decision`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  render();
}

async function editDocument(visitId, docType) {
  const visit = await api(`/api/visits/${visitId}`);
  const current = visit.documents[docType].output;
  const edited = prompt("Edit document text:", current);
  if (edited === null) return;
  await api(`/api/visits/${visitId}/documents/${docType}/decision`, {
    method: "POST",
    body: JSON.stringify({ status: "approved", edited_text: edited, comment: "edited by physician" }),
  });
  render();
}

async function sendDocument(visitId, docType) {
  try {
    await api(`/api/visits/${visitId}/documents/${docType}/send`, { method: "POST" });
  } catch (e) {
    alert("Send blocked: " + e.message);
  }
  render();
}

// ---------- Approval queue ----------

async function renderApprovals() {
  const container = document.getElementById("tab-content");
  const items = await api("/api/approvals");
  container.innerHTML = `
    <section class="panel">
      <h2>Approval queue</h2>
      ${
        items.length
          ? items
              .map(
                (it) => `
        <div class="step">
          <h3>${escapeHtml(it.patient_name)} &mdash; ${DOC_LABELS[it.doc_type] || it.doc_type} <span class="status-badge">${it.status}</span></h3>
          <div class="doc-text">${renderMarkdown(it.output)}</div>
          <div class="review-row">
            <button class="ok" onclick="decideDocument('${it.visit_id}','${it.doc_type}','approved')">Approve</button>
            <button onclick="editDocument('${it.visit_id}','${it.doc_type}')">Edit</button>
            <button class="bad" onclick="decideDocument('${it.visit_id}','${it.doc_type}','rejected')">Reject</button>
            ${
              it.sent
                ? '<span class="approved-yes">sent</span>'
                : `<button ${it.status === "approved" ? "" : "disabled"} onclick="sendDocument('${it.visit_id}','${it.doc_type}')">Send (simulated)</button>`
            }
          </div>
        </div>`
              )
              .join("")
          : '<p class="muted">Nothing waiting.</p>'
      }
    </section>
  `;
}

// ---------- Activity log ----------

async function renderActivity() {
  const container = document.getElementById("tab-content");
  const entries = await api("/api/activity");
  container.innerHTML = `
    <section class="panel">
      <h2>Activity log</h2>
      <ul class="activity-list">
        ${
          entries.length
            ? entries
                .map(
                  (e) => `
          <li>
            <span class="muted">${e.time}</span>
            <strong>${escapeHtml(e.actor)}</strong>: ${escapeHtml(e.action)}
            ${e.detail ? "&mdash; " + escapeHtml(e.detail) : ""}
            ${e.visit_id ? `<span class="status-badge">${e.visit_id}</span>` : ""}
          </li>`
                )
                .join("")
            : '<li class="muted">No activity yet.</li>'
        }
      </ul>
    </section>
  `;
}

// ---------- Placeholders for later build phases ----------

function renderAgentBuilderPlaceholder() {
  document.getElementById("tab-content").innerHTML = `
    <section class="panel">
      <h2>Agent builder</h2>
      <p class="muted">Coming next: describe a tool, gemini-4-argon (Antigravity) writes and tests it against a synthetic 2,500-patient panel, and it appears under My tools.</p>
    </section>`;
}

function renderResultsPlaceholder() {
  document.getElementById("tab-content").innerHTML = `
    <section class="panel">
      <h2>Results</h2>
      <p class="muted">Coming next: 20 synthetic cases run three ways (Flash baseline, Argon agents, Argon agents + verifier) with coverage, errors, and errors caught.</p>
    </section>`;
}

function renderPracticePlaceholder() {
  document.getElementById("tab-content").innerHTML = `
    <section class="panel">
      <h2>Practice setup</h2>
      <p class="muted">Coming next: practice name, hours, visit fee, booking link, and QR code.</p>
    </section>`;
}

function renderBookingPlaceholder() {
  document.getElementById("tab-content").innerHTML = `
    <section class="panel">
      <h2>Booking page (public)</h2>
      <p class="muted">Coming next: public booking form - name, DOB, reason, symptom questions, file upload. Banner: "Use made-up information only."</p>
    </section>`;
}

// ---------- Header controls ----------

async function initHeader() {
  const flags = await api("/api/demo/flags");
  const toggle = document.getElementById("demo-error-toggle");
  toggle.checked = !!flags.DEMO_PLANTED_ERROR;
  toggle.addEventListener("change", async () => {
    await api("/api/demo/flags/DEMO_PLANTED_ERROR", {
      method: "POST",
      body: JSON.stringify({ value: toggle.checked }),
    });
  });
}

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

initHeader();
render();
