const state = { currentTab: "visits", activeVisitId: null, activeBuildToolId: null };
let buildPollTimer = null;

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

function formatStatus(status) {
  if (!status) return "";
  return status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function formatApptTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch (e) {
    return iso;
  }
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
    "agent-builder": renderAgentBuilder,
    results: renderResults,
    practice: renderPractice,
    booking: renderBookingPlaceholder,
  };
  (map[state.currentTab] || renderVisits)();
}

// ---------- Visits ----------

async function renderVisits() {
  const container = document.getElementById("tab-content");
  const visits = await api("/api/visits");
  container.innerHTML = `
    <div class="visits-layout">
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
                <span class="status-badge">${formatStatus(v.status)}</span>
                ${v.appointment_time ? `<span class="status-badge">${formatApptTime(v.appointment_time)}</span>` : ""}
                ${v.payment_status === "paid (simulated)" ? '<span class="status-badge badge-paid">Paid (simulated)</span>' : ""}
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
    <p>
      <span class="status-badge">${formatStatus(v.status)}</span>
      ${v.appointment_time ? `<span class="status-badge">${formatApptTime(v.appointment_time)}</span>` : ""}
      ${v.payment_status === "paid (simulated)" ? '<span class="status-badge badge-paid">Paid (simulated)</span>' : '<span class="muted">Unpaid</span>'}
    </p>
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

// ---------- Agent builder ----------

function toolCard(tool) {
  if (tool.status === "in_progress") {
    return `
      <div class="step">
        <h3>${escapeHtml(tool.description)} <span class="status-badge">in progress</span></h3>
        <p class="muted">${escapeHtml(tool.progress_label || "Working...")}</p>
      </div>`;
  }
  const passedBadge =
    tool.tests_passed === true
      ? '<span class="approved-yes">tests passed</span>'
      : tool.tests_passed === false
      ? '<span class="approved-no">tests failed</span>'
      : '<span class="muted">tests: unknown</span>';
  let countLine = "";
  if (tool.final_count !== null && tool.final_count !== undefined) {
    if (tool.true_count !== null && tool.true_count !== undefined) {
      countLine = tool.count_matches
        ? `<span class="approved-yes">count ${tool.final_count} matches panel's true count (${tool.true_count})</span>`
        : `<span class="approved-no">count ${tool.final_count} does NOT match panel's true count (${tool.true_count})</span>`;
    } else {
      countLine = `<span class="muted">reported count: ${tool.final_count} (no ground truth to check against for this task)</span>`;
    }
  }
  return `
    <div class="step">
      <h3>${escapeHtml(tool.description)} <span class="status-badge">${tool.status}</span></h3>
      <p>${passedBadge} ${countLine}</p>
      <details>
        <summary>Full build log</summary>
        <div class="doc-text">${renderMarkdown(tool.output)}</div>
      </details>
    </div>`;
}

async function renderAgentBuilder() {
  const container = document.getElementById("tab-content");
  const tools = await api("/api/tools");
  container.innerHTML = `
    <section class="panel">
      <h2>Agent builder</h2>
      <p class="muted">
        Describe a back-office tool. This spins up a real Antigravity sandbox running gemini-4-argon,
        which writes the tool, writes tests, runs them against a synthetic 2,500-patient panel, and
        fixes failures until they pass &mdash; not a mock. Costs real API usage and can take several minutes.
      </p>
      <textarea id="tool-description" rows="3" placeholder="e.g. find all my patients with diabetes and track their visits and A1c"></textarea>
      <button id="build-tool-btn">Build &amp; test tool</button>
      <div id="build-tool-status" class="muted"></div>
    </section>
    <section class="panel">
      <h2>My tools</h2>
      <div id="tools-list">
        ${tools.length ? tools.map(toolCard).join("") : '<p class="muted">No tools built yet.</p>'}
      </div>
    </section>
  `;
  document.getElementById("build-tool-btn").addEventListener("click", async () => {
    const description = document.getElementById("tool-description").value.trim();
    if (!description) return;
    const btn = document.getElementById("build-tool-btn");
    const status = document.getElementById("build-tool-status");
    btn.disabled = true;
    status.textContent = "Starting sandbox...";
    try {
      const tool = await api("/api/tools/build/start", {
        method: "POST",
        body: JSON.stringify({ description }),
      });
      state.activeBuildToolId = tool.id;
      pollToolBuild(tool.id);
    } catch (e) {
      status.textContent = "Build failed: " + e.message;
      btn.disabled = false;
    }
  });
  if (state.activeBuildToolId) {
    pollToolBuild(state.activeBuildToolId);
  }
}

function pollToolBuild(toolId) {
  if (buildPollTimer) clearInterval(buildPollTimer);
  buildPollTimer = setInterval(async () => {
    try {
      const tool = await api(`/api/tools/${toolId}/status`);
      const status = document.getElementById("build-tool-status");
      if (status) status.textContent = tool.progress_label || tool.status;
      if (tool.status !== "in_progress") {
        clearInterval(buildPollTimer);
        buildPollTimer = null;
        state.activeBuildToolId = null;
        if (state.currentTab === "agent-builder") render();
      }
    } catch (e) {
      clearInterval(buildPollTimer);
      buildPollTimer = null;
      state.activeBuildToolId = null;
      const status = document.getElementById("build-tool-status");
      if (status) status.textContent = "Build failed: " + e.message;
    }
  }, 3000);
}

let resultsPollTimer = null;

function errorsBarChart(table) {
  const maxVal = Math.max(...table.map((r) => r.avg_errors_per_doc), 0.01);
  const barWidth = 90, gap = 50, chartHeight = 140, leftPad = 20, topPad = 24;
  const bars = table
    .map((r, i) => {
      const h = Math.max(2, Math.round((r.avg_errors_per_doc / maxVal) * chartHeight));
      const x = leftPad + i * (barWidth + gap);
      const y = topPad + (chartHeight - h);
      return `
      <rect x="${x}" y="${y}" width="${barWidth}" height="${h}" fill="#2563eb" rx="3"></rect>
      <text x="${x + barWidth / 2}" y="${y - 8}" text-anchor="middle" font-size="13" fill="#1f2937" font-weight="600">${r.avg_errors_per_doc}</text>
      <text x="${x + barWidth / 2}" y="${topPad + chartHeight + 20}" text-anchor="middle" font-size="11" fill="#6b7280">${escapeHtml(r.method)}</text>
    `;
    })
    .join("");
  const width = leftPad * 2 + table.length * barWidth + (table.length - 1) * gap;
  return `
    <div style="overflow-x:auto;">
      <svg width="${width}" height="${topPad + chartHeight + 36}" viewBox="0 0 ${width} ${topPad + chartHeight + 36}">
        <line x1="${leftPad - 10}" y1="${topPad + chartHeight}" x2="${width - leftPad + 10}" y2="${topPad + chartHeight}" stroke="#dfe3e8"></line>
        ${bars}
      </svg>
    </div>`;
}

function resultsSummarySentence(table) {
  const baseline = table.find((r) => r.method === "Flash baseline");
  const argon = table.find((r) => r.method === "Argon agents");
  const verified = table.find((r) => r.method === "Argon agents + verifier");
  if (!baseline || !argon || !verified || !argon.avg_errors_per_doc) return "";
  const ratio = baseline.avg_errors_per_doc / argon.avg_errors_per_doc;
  return `Argon agents made about ${ratio.toFixed(1)}x fewer errors than the Flash baseline; the verifier caught ${verified.errors_caught_total} errors before physician review.`;
}

function resultsTableHtml(run) {
  if (!run || run.status === "never_run") return '<p class="muted">No batch run yet.</p>';
  if (run.status === "failed") return `<p class="approved-no">Batch failed: ${escapeHtml(run.error || "unknown error")}</p>`;
  if (run.status === "in_progress" || !run.table) return '<p class="muted">Results will appear here once the run completes.</p>';
  const rows = run.table
    .map(
      (r) => `
    <tr>
      <td>${escapeHtml(r.method)}</td>
      <td>${r.coverage_pct}%</td>
      <td>${r.avg_errors_per_doc}</td>
      <td>${r.errors_caught_total}</td>
      <td>${r.avg_time_per_doc_sec}s</td>
      <td>${r.total_tokens.toLocaleString()}</td>
    </tr>`
    )
    .join("");
  return `
    <p class="muted">Completed in ${run.elapsed_seconds ? Math.round(run.elapsed_seconds) + "s" : "?"} (${run.completed}/${run.total} documents, run finished ${run.finished_at || ""}).</p>
    <p><strong>${resultsSummarySentence(run.table)}</strong></p>
    <h3>Errors per document, by method</h3>
    ${errorsBarChart(run.table)}
    <div style="overflow-x:auto;">
    <table class="results-table">
      <thead>
        <tr><th>Method</th><th>Coverage</th><th>Avg errors/doc</th><th>Errors caught (total)</th><th>Avg time/doc</th><th>Total tokens (cost proxy)</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
  `;
}

async function renderResults() {
  const container = document.getElementById("tab-content");
  const run = await api("/api/results");
  container.innerHTML = `
    <section class="panel">
      <h2>Results</h2>
      <p class="muted">
        10 synthetic cases &times; 3 document types (note, prescription, prior auth) run three ways:
        Flash baseline (single gemini-3.8-flash call, no specialized prompts), Argon agents (gemini-4-argon with
        the real specialized prompts, single draft), and Argon agents + verifier (the real blocking verify-and-revise
        loop). Baseline and Argon-agents-only are graded after the fact by one independent verifier pass each, so
        errors are measured the same way across all three. Runs concurrently across cases and methods.
      </p>
      <button id="run-results-btn" ${run.status === "in_progress" ? "disabled" : ""}>Run batch</button>
      <div id="results-status" class="muted">${run.status === "in_progress" ? `Running... (${run.completed}/${run.total})` : ""}</div>
    </section>
    <section class="panel">
      ${resultsTableHtml(run)}
    </section>
  `;
  document.getElementById("run-results-btn").addEventListener("click", async () => {
    document.getElementById("run-results-btn").disabled = true;
    await api("/api/results/run", { method: "POST" });
    pollResults();
  });
  if (run.status === "in_progress") pollResults();
}

function pollResults() {
  if (resultsPollTimer) clearInterval(resultsPollTimer);
  resultsPollTimer = setInterval(async () => {
    try {
      const run = await api("/api/results");
      const status = document.getElementById("results-status");
      if (status) status.textContent = run.status === "in_progress" ? `Running... (${run.completed}/${run.total})` : "";
      if (run.status !== "in_progress") {
        clearInterval(resultsPollTimer);
        resultsPollTimer = null;
        if (state.currentTab === "results") render();
      }
    } catch (e) {
      clearInterval(resultsPollTimer);
      resultsPollTimer = null;
    }
  }, 3000);
}

async function renderPractice() {
  const container = document.getElementById("tab-content");
  const practice = await api("/api/practice");
  const earnings = await api("/api/earnings");
  const flags = await api("/api/demo/flags");
  let ngrokUrl = null;
  try {
    const r = await api("/api/ngrok-url");
    ngrokUrl = r.url;
  } catch (e) {
    ngrokUrl = null;
  }
  const origin = ngrokUrl || window.location.origin;
  const bookingUrl = `${origin}/book`;
  const ngrokNote = ngrokUrl
    ? '<p class="muted">Using the live ngrok tunnel - this code works from any phone.</p>'
    : '<p class="approved-no">ngrok isn\'t running - this falls back to the current page\'s URL, which won\'t be phone-reachable if that\'s localhost. Run <code>./start_demo.sh</code> to get a real tunnel.</p>';
  container.innerHTML = `
    <section class="panel">
      <h2>Practice setup</h2>
      <label>Practice name (patient-facing)</label>
      <input id="p-name" type="text" value="${escapeHtml(practice.name)}">
      <label>Physician name</label>
      <input id="p-physician" type="text" value="${escapeHtml(practice.physician_name)}">
      <label>Hours</label>
      <input id="p-hours" type="text" value="${escapeHtml(practice.hours)}">
      <label>Visit fee</label>
      <input id="p-fee" type="text" value="${escapeHtml(practice.visit_fee)}">
      <button id="p-save-btn">Save</button>
      <div id="p-save-status" class="muted"></div>
      <p class="muted">Practice earnings (simulated): ${earnings.paid_visit_count} paid visit${earnings.paid_visit_count === 1 ? "" : "s"}, $${earnings.total_amount.toFixed(2)} total.</p>
      <label class="flag-toggle" style="margin-top:1rem;">
        <input type="checkbox" id="demo-error-toggle" ${flags.DEMO_PLANTED_ERROR ? "checked" : ""}>
        Verifier demo: insert an outdated lab value into Margaret's first draft
      </label>
    </section>
    <section class="panel" id="qr-screen">
      <h2>Booking link</h2>
      <p class="muted">Patients scan this to open the booking page on their phone.</p>
      <p><code>${escapeHtml(bookingUrl)}</code></p>
      <div style="text-align:center; padding: 1rem;">
        <img src="/api/qr?url=${encodeURIComponent(bookingUrl)}" alt="QR code to booking page" style="width:260px;height:260px;">
      </div>
      ${ngrokNote}
    </section>
  `;
  document.getElementById("p-save-btn").addEventListener("click", async () => {
    const status = document.getElementById("p-save-status");
    status.textContent = "Saving...";
    try {
      await api("/api/practice", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("p-name").value,
          physician_name: document.getElementById("p-physician").value,
          hours: document.getElementById("p-hours").value,
          visit_fee: document.getElementById("p-fee").value,
        }),
      });
      status.textContent = "Saved.";
    } catch (e) {
      status.textContent = "Failed: " + e.message;
    }
  });
  document.getElementById("demo-error-toggle").addEventListener("change", async (e) => {
    await api("/api/demo/flags/DEMO_PLANTED_ERROR", {
      method: "POST",
      body: JSON.stringify({ value: e.target.checked }),
    });
  });
}

function renderBookingPlaceholder() {
  document.getElementById("tab-content").innerHTML = `
    <section class="panel">
      <h2>Booking page (public)</h2>
      <p class="muted">
        This is the live public page, open to anyone with the link - it's served at
        <a href="/book" target="_blank" rel="noopener">/book</a>, not behind this dashboard's nav.
        Scan the QR code on the Practice setup tab, or open the link directly.
      </p>
      <iframe src="/book" style="width:100%;height:700px;border:1px solid var(--border);border-radius:8px;"></iframe>
    </section>`;
}

// ---------- Header controls ----------

async function initHeader() {
  document.getElementById("reset-demo-btn").addEventListener("click", async () => {
    if (!confirm("Reset demo? This clears all visits and approvals except Margaret's demo case. My tools, Results, and Practice settings are kept.")) {
      return;
    }
    await api("/api/demo/reset", { method: "POST" });
    state.activeVisitId = null;
    render();
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
