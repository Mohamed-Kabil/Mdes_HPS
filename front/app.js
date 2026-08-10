const STATUS_LABEL = {
  implemente: "Implémenté",
  partiel: "Partiel",
  non_implemente: "Non implémenté",
  unknown: "Inconnu",
};

async function loadPhase1() {
  const el = document.getElementById("phase1-content");
  try {
    const res = await fetch("/api/phase1");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderPhase1(data.apis, data.shared_fixes || [], el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

function renderPhase1(apis, sharedFixes, el) {
  el.className = "";
  el.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "api-grid";

  for (const api of apis) {
    const tile = document.createElement("div");
    tile.className = "api-tile";
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");

    tile.innerHTML = `
      <div class="api-tile-header">
        <span class="status-dot ${api.status}"></span>
        <span class="api-name">${api.display}</span>
      </div>
      <div class="api-path">${api.path}</div>
      <span class="api-badge ${api.status}">${STATUS_LABEL[api.status] || api.status}</span>
      <div class="no-match-note">${api.reliable_issues} écart(s) fiable(s) sur ${api.total_fields} champ(s)</div>
    `;
    tile.addEventListener("click", () => openFieldModal(api));
    tile.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") openFieldModal(api);
    });
    grid.appendChild(tile);
  }

  el.appendChild(grid);
  renderSharedFixes(sharedFixes, el);
}

// ---------------------------------------------------------------------------
// "Fix once" — divergences that trace back to the exact same shared schema
// ($ref target) on both pre-dig.yaml and data.yaml across 2+ endpoints, so
// fixing that one data.yaml schema resolves all of them at once. Purely
// structural (see group_shared_schema_fixes() in phase1_historical_audit.py).
// ---------------------------------------------------------------------------

function renderSharedFixes(sharedFixes, container) {
  if (!sharedFixes || !sharedFixes.length) return;

  const section = document.createElement("div");
  section.className = "shared-fixes";

  const heading = document.createElement("h3");
  heading.className = "shared-fixes-heading";
  heading.textContent = "Écarts à cause commune — corriger une fois pour résoudre plusieurs endpoints";
  section.appendChild(heading);

  for (const target of sharedFixes) {
    const card = document.createElement("details");
    card.className = "shared-fix-card";

    const summary = document.createElement("summary");
    summary.innerHTML = `Corriger <code>${target.data_origin}</code> dans data.yaml → résout
      <strong>${target.field_count} champ(s)</strong> sur <strong>${target.endpoint_count} endpoint(s)</strong>
      d'un coup : ${target.endpoints.join(", ")}`;
    card.appendChild(summary);

    const body = document.createElement("div");
    body.className = "shared-fix-body";
    for (const schema of target.schemas) {
      const block = document.createElement("div");
      block.className = "shared-fix-schema";
      block.innerHTML = `<div class="shared-fix-schema-name">via pre-dig.yaml <code>${schema.predig_origin}</code>
        (${schema.field_count} champ(s))</div>`;
      const list = document.createElement("ul");
      for (const f of schema.fields) {
        const li = document.createElement("li");
        li.innerHTML = `${f.name} <span class="field-lines">${formatFieldLines({
          predig_line: f.predig_line,
          data_line: f.data_line,
        })}</span>`;
        list.appendChild(li);
      }
      block.appendChild(list);
      body.appendChild(block);
    }
    card.appendChild(body);
    section.appendChild(card);
  }

  container.appendChild(section);
}

// ---------------------------------------------------------------------------
// Modal — field-level detail for one API, opened by clicking its tile
// ---------------------------------------------------------------------------

const modalOverlay = document.getElementById("modal-overlay");
const modalTitle = document.getElementById("modal-title");
const modalBody = document.getElementById("modal-body");
document.getElementById("modal-close").addEventListener("click", closeModal);
modalOverlay.addEventListener("click", (e) => {
  if (e.target === modalOverlay) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

function closeModal() {
  modalOverlay.classList.add("hidden");
}

function openFieldModal(api) {
  modalTitle.textContent = `${api.display} — ${api.path}`;
  modalBody.innerHTML = "";
  modalBody.classList.remove("report-view");

  const state = { mode: "issues", requis: "all" };

  const filterBar = document.createElement("div");
  filterBar.className = "field-filter";
  const filters = [
    { key: "issues", label: `Écarts fiables (${api.reliable_issues})` },
    { key: "all", label: `Tous les champs (${api.total_fields})` },
  ];
  filters.forEach((f, i) => {
    const btn = document.createElement("button");
    btn.textContent = f.label;
    btn.className = i === 0 ? "active" : "";
    btn.addEventListener("click", () => {
      filterBar.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mode = f.key;
      renderFieldTable(api.fields, state, tableWrap);
    });
    filterBar.appendChild(btn);
  });
  modalBody.appendChild(filterBar);

  const requisBar = document.createElement("div");
  requisBar.className = "field-filter requis-filter";
  const requisLabel = document.createElement("label");
  requisLabel.setAttribute("for", "requis-select");
  requisLabel.textContent = "Requis";
  const requisSelect = document.createElement("select");
  requisSelect.id = "requis-select";
  [
    { key: "all", label: "Tous" },
    { key: "yes", label: "Oui" },
    { key: "no", label: "Non" },
  ].forEach((r) => {
    const option = document.createElement("option");
    option.value = r.key;
    option.textContent = r.label;
    requisSelect.appendChild(option);
  });
  requisSelect.addEventListener("change", () => {
    state.requis = requisSelect.value;
    renderFieldTable(api.fields, state, tableWrap);
  });
  requisBar.appendChild(requisLabel);
  requisBar.appendChild(requisSelect);
  modalBody.appendChild(requisBar);

  const tableWrap = document.createElement("div");
  tableWrap.className = "field-table-wrap";
  modalBody.appendChild(tableWrap);
  renderFieldTable(api.fields, state, tableWrap);

  modalOverlay.classList.remove("hidden");
}

function formatFieldLines(f) {
  const parts = [];
  if (f.predig_line) parts.push(`pre-dig:${f.predig_line}`);
  if (f.data_line) parts.push(`data:${f.data_line}`);
  return parts.length ? parts.join(" · ") : "—";
}

function renderFieldTable(fields, state, container) {
  let shown =
    state.mode === "issues"
      ? fields.filter((f) => f.status !== "implemente" && f.reliable)
      : fields;

  if (state.requis === "yes") {
    shown = shown.filter((f) => f.required === true);
  } else if (state.requis === "no") {
    shown = shown.filter((f) => f.required === false);
  }

  if (!shown.length) {
    container.innerHTML = `<p class="no-match-note">Aucun champ à afficher.</p>`;
    return;
  }

  const rows = shown
    .map(
      (f) => `
      <tr>
        <td class="field-name">${f.name}</td>
        <td><span class="field-status-badge ${f.status}">${STATUS_LABEL[f.status] || f.status}</span></td>
        <td>${f.type ?? "—"}</td>
        <td>${f.minLength ?? "—"}</td>
        <td>${f.maxLength ?? "—"}</td>
        <td>${f.required === true ? "Oui" : f.required === false ? "Non" : "—"}</td>
        <td class="field-reasons">${(f.reasons || []).join("; ") || "—"}</td>
        <td class="field-lines">${formatFieldLines(f)}</td>
      </tr>`
    )
    .join("");

  container.innerHTML = `
    <table class="field-table">
      <thead>
        <tr>
          <th>Champ</th>
          <th>Statut</th>
          <th>Type</th>
          <th>Min</th>
          <th>Max</th>
          <th>Requis</th>
          <th>Écart(s)</th>
          <th>Ligne</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ---------------------------------------------------------------------------
// MDES Customer Service — écarts spec officiel vs Java (mdes_cs_divergence_report.py)
// ---------------------------------------------------------------------------

const CS_DIVERGENCE_STATUS_LABEL = {
  implemente: "Implémenté",
  partiel: "Partiel (inféré par le modèle)",
  non_verifiable: "Non vérifiable — écart dans la donnée",
  non_implemente: "Non implémenté",
};

async function loadMdesCsDivergence() {
  const el = document.getElementById("mdes-cs-divergence-content");
  try {
    const res = await fetch("/api/mdes_cs_divergence");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderMdesCsDivergence(data, el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

function worstCsStatus(counts) {
  if (counts.non_implemente) return "non_implemente";
  if (counts.non_verifiable) return "partiel";
  if (counts.partiel) return "partiel";
  return "implemente";
}

// ---------------------------------------------------------------------------
// "Fix once" pour le volet CS — champs non_implemente identiques partagés
// par 2+ opérations à la fois (voir group_shared_field_gaps() /
// summarize_by_root_field() dans mdes_cs_divergence_report.py). Même idée
// que renderSharedFixes() côté pre-dig, mais sans le double niveau
// schéma pre-dig/data.yaml -- ici la clé partagée est directement le champ.
// ---------------------------------------------------------------------------

function renderCsSharedGaps(sharedGaps, container) {
  if (!sharedGaps || !sharedGaps.length) return;

  const section = document.createElement("div");
  section.className = "shared-fixes";

  const heading = document.createElement("h3");
  heading.className = "shared-fixes-heading";
  heading.textContent = "Écarts à cause commune — corriger une fois pour résoudre plusieurs opérations";
  section.appendChild(heading);

  for (const g of sharedGaps) {
    const card = document.createElement("details");
    card.className = "shared-fix-card";

    const summary = document.createElement("summary");
    summary.innerHTML = `Corriger <code>${g.root_field}</code> côté Java → résout
      <strong>${g.field_count} champ(s)</strong> sur <strong>${g.operation_count} opération(s)</strong>
      d'un coup : ${g.operations.join(", ")}`;
    card.appendChild(summary);

    const body = document.createElement("div");
    body.className = "shared-fix-body";
    const list = document.createElement("ul");
    for (const field of g.fields) {
      const li = document.createElement("li");
      li.textContent = field;
      list.appendChild(li);
    }
    body.appendChild(list);
    card.appendChild(body);
    section.appendChild(card);
  }

  container.appendChild(section);
}

function renderMdesCsDivergence(data, el) {
  el.className = "";
  el.innerHTML = "";

  const meta = document.createElement("div");
  meta.className = "release-meta";
  meta.innerHTML = `<span>Spec officiel : ${data.spec_source}</span><span>Extraction Java du ${data.java_mapping_generated_at}</span>`;
  el.appendChild(meta);

  const grid = document.createElement("div");
  grid.className = "api-grid";

  for (const op of data.operations) {
    if (op.error) continue;
    const c = op.counts || {};
    const status = worstCsStatus(c);
    const issues = (c.non_implemente || 0) + (c.non_verifiable || 0) + (c.partiel || 0);

    const tile = document.createElement("div");
    tile.className = "api-tile";
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");
    tile.innerHTML = `
      <div class="api-tile-header">
        <span class="status-dot ${status}"></span>
        <span class="api-name">${op.operation}</span>
      </div>
      <div class="api-path">${op.path}</div>
      <span class="api-badge ${status}">${STATUS_LABEL[status] || status}</span>
      <div class="no-match-note">${issues} écart(s) sur ${op.total_fields} champ(s)</div>
    `;
    tile.addEventListener("click", () => openMdesCsDivergenceModal(op));
    tile.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") openMdesCsDivergenceModal(op);
    });
    grid.appendChild(tile);
  }

  el.appendChild(grid);
  renderCsSharedGaps(data.shared_gaps || [], el);
}

function openMdesCsDivergenceModal(op) {
  modalTitle.textContent = `${op.operation} — ${op.path}`;
  modalBody.innerHTML = "";
  modalBody.classList.remove("report-view");

  const state = { mode: "issues" };
  const filterBar = document.createElement("div");
  filterBar.className = "field-filter";
  const filters = [
    { key: "issues", label: `Écarts (${op.fields.filter((f) => f.status !== "implemente").length})` },
    { key: "all", label: `Tous les champs (${op.fields.length})` },
  ];
  filters.forEach((f, i) => {
    const btn = document.createElement("button");
    btn.textContent = f.label;
    btn.className = i === 0 ? "active" : "";
    btn.addEventListener("click", () => {
      filterBar.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mode = f.key;
      renderCsDivergenceTable(op.fields, state, tableWrap);
    });
    filterBar.appendChild(btn);
  });
  modalBody.appendChild(filterBar);

  const tableWrap = document.createElement("div");
  tableWrap.className = "field-table-wrap";
  modalBody.appendChild(tableWrap);
  renderCsDivergenceTable(op.fields, state, tableWrap);

  modalOverlay.classList.remove("hidden");
}

function renderCsDivergenceTable(fields, state, container) {
  const shown = state.mode === "issues" ? fields.filter((f) => f.status !== "implemente") : fields;

  if (!shown.length) {
    container.innerHTML = `<p class="no-match-note">Aucun champ à afficher.</p>`;
    return;
  }

  const rows = shown
    .map(
      (f) => `
      <tr>
        <td class="field-name">${f.field}</td>
        <td><span class="field-status-badge ${f.status === "non_verifiable" ? "partiel" : f.status}">${
          CS_DIVERGENCE_STATUS_LABEL[f.status] || f.status
        }</span></td>
        <td>${f.type ?? "—"}</td>
        <td>${f.required ? "Oui" : "Non"}</td>
        <td class="field-lines">${(f.java_source || []).join(", ") || "—"}</td>
      </tr>`
    )
    .join("");

  container.innerHTML = `
    <table class="field-table">
      <thead>
        <tr>
          <th>Champ (spec officiel)</th>
          <th>Statut</th>
          <th>Type</th>
          <th>Requis</th>
          <th>Source Java</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ---------------------------------------------------------------------------
// MDES Customer Service — API -> Java field mapping (generated, read-only)
// ---------------------------------------------------------------------------

const SOURCE_TAG_STATUS = {
  "mechanical-scan": "implemente",
  "llm-inferred": "partiel",
  "unresolved": "non_implemente",
};

const SOURCE_TAG_LABEL = {
  "mechanical-scan": "Trouvé (scan mécanique)",
  "llm-inferred": "Résolu par le modèle local",
  "unresolved": "Non résolu — écart",
};

async function loadMdesCsMapping() {
  const el = document.getElementById("mdes-cs-content");
  try {
    const res = await fetch("/api/mdes_cs_mapping");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderMdesCsMapping(data, el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

function renderMdesCsMapping(data, el) {
  el.className = "";
  el.innerHTML = "";

  if (data.generated_at) {
    const meta = document.createElement("div");
    meta.className = "release-meta";
    meta.innerHTML = `<span>Généré le : ${data.generated_at}</span>`;
    el.appendChild(meta);
  }

  const grid = document.createElement("div");
  grid.className = "api-grid";

  for (const op of data.operations) {
    const status = op.unresolved_count > 0 ? "partiel" : "implemente";
    const tile = document.createElement("div");
    tile.className = "api-tile";
    tile.tabIndex = 0;
    tile.setAttribute("role", "button");

    tile.innerHTML = `
      <div class="api-tile-header">
        <span class="status-dot ${status}"></span>
        <span class="api-name">${op.operation}</span>
      </div>
      <div class="api-path">${op.path}</div>
      <span class="api-badge ${status}">${op.unresolved_count > 0 ? "Écart(s)" : "Résolu"}</span>
      <div class="no-match-note">${op.unresolved_count} champ(s) non résolu(s) sur ${op.total_fields}</div>
    `;
    tile.addEventListener("click", () => openMdesCsModal(op));
    tile.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") openMdesCsModal(op);
    });
    grid.appendChild(tile);
  }

  el.appendChild(grid);
}

function openMdesCsModal(op) {
  modalTitle.textContent = `${op.operation} — ${op.path}`;
  modalBody.innerHTML = "";
  modalBody.classList.remove("report-view");

  const javaFileNote = document.createElement("p");
  javaFileNote.className = "no-match-note";
  javaFileNote.textContent = op.java_file;
  modalBody.appendChild(javaFileNote);

  for (const variant of op.variants) {
    const details = document.createElement("details");
    details.open = op.variants.length === 1;
    details.className = "shared-fix-card";

    const summary = document.createElement("summary");
    summary.innerHTML = `Variante <code>${variant.name}</code>${
      variant.builder_method ? ` — <code>${variant.builder_method}()</code>` : ""
    }${variant.source_lines ? ` (lignes ${variant.source_lines})` : ""} — ${variant.fields.length} champ(s)`;
    details.appendChild(summary);

    const rows = variant.fields
      .map(
        (f) => `
        <tr>
          <td class="field-name">${f.path}</td>
          <td>${f.type ?? "—"}</td>
          <td><span class="field-status-badge ${SOURCE_TAG_STATUS[f.source] || ""}">${
            SOURCE_TAG_LABEL[f.source] || f.source
          }</span></td>
          <td class="field-lines">${f.java_source ?? "—"}</td>
        </tr>`
      )
      .join("");

    const tableWrap = document.createElement("div");
    tableWrap.className = "field-table-wrap";
    tableWrap.innerHTML = `
      <table class="field-table">
        <thead>
          <tr>
            <th>Champ</th>
            <th>Type</th>
            <th>Statut</th>
            <th>Source Java</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    details.appendChild(tableWrap);
    modalBody.appendChild(details);
  }

  modalOverlay.classList.remove("hidden");
}

async function loadPhase2() {
  const el = document.getElementById("phase2-content");
  try {
    const res = await fetch("/api/phase2/latest");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderPhase2(data, el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

function renderPhase2(data, el) {
  el.className = "";
  el.innerHTML = "";

  const card = document.createElement("div");
  card.className = "release-card";

  const chips = data.tracked_apis
    .map((api) => {
      const matched = data.matched_apis.includes(api);
      return `<span class="chip ${matched ? "matched" : "unmatched"}">${api}</span>`;
    })
    .join("");

  const matchNote = data.matched_apis.length
    ? `<div class="matched-apis">${chips}</div>`
    : `<div class="no-match-note">Aucune des ${data.tracked_apis.length} APIs suivies n'est mentionnée dans cette release.</div>
       <div class="matched-apis">${chips}</div>`;

  card.innerHTML = `
    <div class="release-title">${data.title}</div>
    <div class="release-meta">
      <span><strong>Version :</strong> ${data.mdes_release}</span>
      <span><strong>Type :</strong> ${data.note_type}</span>
      <span><strong>Date :</strong> ${data.upgrade_date}</span>
    </div>
    ${matchNote}
    <a class="release-link" href="${data.url}" target="_blank" rel="noopener">Voir la release note sur developer.mastercard.com →</a>
  `;

  el.appendChild(card);
}

// ---------------------------------------------------------------------------
// MDES Customer Service — dernière pre-release Mastercard (mdes_cs_prereleases.py)
// ---------------------------------------------------------------------------

async function loadMdesCsPrereleases() {
  const el = document.getElementById("mdes-cs-prereleases-content");
  try {
    const res = await fetch("/api/mdes_cs_prereleases/latest");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderCsPrereleases(data, el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

function renderCsPrereleases(data, el) {
  el.className = "";
  el.innerHTML = "";

  const card = document.createElement("div");
  card.className = "release-card";

  const chips = data.tracked_apis
    .map((api) => {
      const matched = data.matched_apis.includes(api);
      return `<span class="chip ${matched ? "matched" : "unmatched"}">${api}</span>`;
    })
    .join("");

  const matchNote = data.matched_apis.length
    ? `<div class="matched-apis">${chips}</div>`
    : `<div class="no-match-note">Aucune des ${data.tracked_apis.length} opérations suivies n'est mentionnée dans cette release.</div>
       <div class="matched-apis">${chips}</div>`;

  card.innerHTML = `
    <div class="release-title">${data.title}</div>
    <div class="release-meta">
      <span><strong>Date :</strong> ${data.upgrade_date}</span>
    </div>
    ${matchNote}
    <a class="release-link" href="${data.url}" target="_blank" rel="noopener">Voir la release note sur developer.mastercard.com →</a>
  `;

  el.appendChild(card);
}

function handleCsPrereleaseCheckResult(data, statusEl, contextLabel) {
  statusEl.innerHTML = "";

  if (data.outcome === "no_new") {
    setStatus(statusEl, "success", "Aucune nouvelle release CS à signaler.");
    openInfoModal(
      "Aucune nouvelle release",
      `Aucune nouvelle release Mastercard CS depuis la dernière vérification (${contextLabel}).`
    );
  } else if (data.outcome === "new_no_impact") {
    setStatus(
      statusEl,
      "success",
      `${data.checked_count} nouvelle(s) release(s) CS — aucune n'affecte les opérations suivies.`
    );
    openInfoModal(
      "Aucun impact sur les opérations suivies",
      `${data.checked_count} nouvelle(s) release(s) CS trouvée(s) (${contextLabel}), mais aucune ne mentionne une opération suivie :`,
      data.checked_titles
    );
  } else {
    setStatus(statusEl, "success", `${data.relevant_titles.length} release(s) touchent ${data.matched_apis.join(", ")} — `);
    const sendBtn = document.createElement("button");
    sendBtn.className = "action-btn inline-action-btn";
    sendBtn.textContent = "Vérifier et envoyer l'email…";
    sendBtn.addEventListener("click", () => {
      openEmailPreviewModal("/api/mdes_cs_prereleases/send", data.subject, data.body, { report_path: data.report_path }, () => loadReports());
    });
    statusEl.appendChild(sendBtn);
  }
  loadMdesCsPrereleases();
  loadReports();
}

document.getElementById("mdes-cs-prereleases-check-pending-btn").addEventListener("click", () => {
  const btn = document.getElementById("mdes-cs-prereleases-check-pending-btn");
  const statusEl = document.getElementById("mdes-cs-prereleases-status");

  runAction(btn, statusEl, "/api/mdes_cs_prereleases/check-pending", {}, (data) => {
    handleCsPrereleaseCheckResult(data, statusEl, "toutes les releases après le dernier audit CS");
  });
});

document.getElementById("mdes-cs-prereleases-check-latest-btn").addEventListener("click", () => {
  const btn = document.getElementById("mdes-cs-prereleases-check-latest-btn");
  const statusEl = document.getElementById("mdes-cs-prereleases-status");

  runAction(btn, statusEl, "/api/mdes_cs_prereleases/check-latest", {}, (data) => {
    const contextLabel = data.used_fallback
      ? "aucun contrôle 'après le dernier audit CS' n'a encore été fait — dernière release uniquement"
      : "depuis le dernier contrôle 'après le dernier audit CS'";
    handleCsPrereleaseCheckResult(data, statusEl, contextLabel);
  });
});

// ---------------------------------------------------------------------------
// Actions — re-run Phase 1 / Phase 2 on demand (step 4)
// ---------------------------------------------------------------------------

function setStatus(el, mode, text) {
  el.className = `action-status ${mode}`;
  el.textContent = text;
}

async function runAction(btn, statusEl, url, extraBody, onDone) {
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "En cours…";
  setStatus(statusEl, "pending", "Exécution en cours — ça peut prendre un moment…");

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(extraBody),
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus(statusEl, "error", data.error || "Erreur inconnue.");
      return;
    }
    onDone(data, statusEl);
  } catch (e) {
    setStatus(statusEl, "error", "Impossible de contacter le serveur (" + e.message + ").");
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

// ---------------------------------------------------------------------------
// Email preview/edit popup — shown before ANY send, never auto-sent
// ---------------------------------------------------------------------------

function openEmailPreviewModal(sendUrl, subject, body, extraSendFields, onSent) {
  modalTitle.textContent = "Vérifier avant l'envoi";
  modalBody.innerHTML = "";
  modalBody.classList.remove("report-view");

  const subjectLabel = document.createElement("label");
  subjectLabel.className = "email-field-label";
  subjectLabel.textContent = "Objet";
  const subjectInput = document.createElement("input");
  subjectInput.type = "text";
  subjectInput.className = "email-subject-input";
  subjectInput.value = subject;

  const bodyLabel = document.createElement("label");
  bodyLabel.className = "email-field-label";
  bodyLabel.textContent = "Corps";
  const bodyTextarea = document.createElement("textarea");
  bodyTextarea.className = "email-body-textarea";
  bodyTextarea.value = body;

  const feedback = document.createElement("div");
  feedback.className = "action-status";

  const footer = document.createElement("div");
  footer.className = "email-preview-footer";
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "action-btn";
  cancelBtn.textContent = "Annuler";
  cancelBtn.addEventListener("click", closeModal);
  const sendBtn = document.createElement("button");
  sendBtn.className = "action-btn primary";
  sendBtn.textContent = "Envoyer";

  sendBtn.addEventListener("click", async () => {
    sendBtn.disabled = true;
    sendBtn.textContent = "Envoi…";
    setStatus(feedback, "pending", "Envoi en cours…");
    try {
      const res = await fetch(sendUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject: subjectInput.value, body: bodyTextarea.value, ...extraSendFields }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        setStatus(feedback, "error", data.error || "Erreur inconnue.");
        sendBtn.disabled = false;
        sendBtn.textContent = "Envoyer";
        return;
      }
      setStatus(feedback, "success", `Email envoyé à ${data.sent_to.join(", ")}.`);
      sendBtn.textContent = "Envoyé";
      cancelBtn.textContent = "Fermer";
      if (onSent) onSent(data);
    } catch (e) {
      setStatus(feedback, "error", "Erreur réseau : " + e.message);
      sendBtn.disabled = false;
      sendBtn.textContent = "Envoyer";
    }
  });

  footer.appendChild(cancelBtn);
  footer.appendChild(sendBtn);

  modalBody.appendChild(subjectLabel);
  modalBody.appendChild(subjectInput);
  modalBody.appendChild(bodyLabel);
  modalBody.appendChild(bodyTextarea);
  modalBody.appendChild(feedback);
  modalBody.appendChild(footer);

  modalOverlay.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Info popup — generic modal for phase 2's "nothing to report" outcomes
// (no new release / new release(s) but none impact a tracked API).
// ---------------------------------------------------------------------------

function openInfoModal(title, message, items) {
  modalTitle.textContent = title;
  modalBody.innerHTML = "";
  modalBody.classList.remove("report-view");

  const p = document.createElement("p");
  p.className = "no-match-note";
  p.textContent = message;
  modalBody.appendChild(p);

  if (items && items.length) {
    const ul = document.createElement("ul");
    ul.className = "info-modal-list";
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      ul.appendChild(li);
    }
    modalBody.appendChild(ul);
  }

  modalOverlay.classList.remove("hidden");
}

function handlePhase2CheckResult(data, statusEl, contextLabel) {
  statusEl.innerHTML = "";

  if (data.outcome === "no_new") {
    setStatus(statusEl, "success", "Aucune nouvelle release à signaler.");
    openInfoModal(
      "Aucune nouvelle release",
      `Aucune nouvelle release Mastercard depuis la dernière vérification (${contextLabel}).`
    );
  } else if (data.outcome === "new_no_impact") {
    setStatus(
      statusEl,
      "success",
      `${data.checked_count} nouvelle(s) release(s) — aucune n'affecte les APIs suivies.`
    );
    openInfoModal(
      "Aucun impact sur les APIs suivies",
      `${data.checked_count} nouvelle(s) release(s) trouvée(s) (${contextLabel}), mais aucune ne mentionne une API suivie :`,
      data.checked_titles
    );
  } else {
    setStatus(statusEl, "success", `${data.relevant_titles.length} release(s) touchent ${data.matched_apis.join(", ")} — `);
    const sendBtn = document.createElement("button");
    sendBtn.className = "action-btn inline-action-btn";
    sendBtn.textContent = "Vérifier et envoyer l'email…";
    sendBtn.addEventListener("click", () => {
      openEmailPreviewModal("/api/phase2/send", data.subject, data.body, { report_path: data.report_path }, () => loadReports());
    });
    statusEl.appendChild(sendBtn);
  }
  loadPhase2();
  loadReports();
}

document.getElementById("phase2-check-pending-btn").addEventListener("click", () => {
  const btn = document.getElementById("phase2-check-pending-btn");
  const statusEl = document.getElementById("phase2-status");

  runAction(btn, statusEl, "/api/phase2/check-pending", {}, (data) => {
    handlePhase2CheckResult(data, statusEl, "toutes les releases après le dernier pre-dig");
  });
});

document.getElementById("phase2-check-latest-btn").addEventListener("click", () => {
  const btn = document.getElementById("phase2-check-latest-btn");
  const statusEl = document.getElementById("phase2-status");

  runAction(btn, statusEl, "/api/phase2/check-latest", {}, (data) => {
    const contextLabel = data.used_fallback
      ? "aucun contrôle 'après le dernier pre-dig' n'a encore été fait — dernière release uniquement"
      : "depuis le dernier contrôle 'après le dernier pre-dig'";
    handlePhase2CheckResult(data, statusEl, contextLabel);
  });
});

document.getElementById("phase1-run-btn").addEventListener("click", () => {
  const btn = document.getElementById("phase1-run-btn");
  const statusEl = document.getElementById("phase1-status");

  runAction(btn, statusEl, "/api/phase1/run", { cutoff: "2025-01" }, (data) => {
    statusEl.innerHTML = "";
    setStatus(statusEl, "success", `Audit terminé (${data.releases_audited} release(s)) — `);
    const sendBtn = document.createElement("button");
    sendBtn.className = "action-btn inline-action-btn";
    sendBtn.textContent = "Vérifier et envoyer l'email…";
    sendBtn.addEventListener("click", () => {
      openEmailPreviewModal("/api/phase1/send", data.subject, data.body, { report_path: data.report_path }, () => loadReports());
    });
    statusEl.appendChild(sendBtn);
    loadPhase1();
    loadReports();
  });
});

document.getElementById("mdes-cs-run-btn").addEventListener("click", () => {
  const btn = document.getElementById("mdes-cs-run-btn");
  const statusEl = document.getElementById("mdes-cs-divergence-status");

  runAction(btn, statusEl, "/api/mdes_cs_divergence/run", {}, (data) => {
    statusEl.innerHTML = "";
    setStatus(statusEl, "success", "Audit CS terminé — ");
    const sendBtn = document.createElement("button");
    sendBtn.className = "action-btn inline-action-btn";
    sendBtn.textContent = "Vérifier et envoyer l'email…";
    sendBtn.addEventListener("click", () => {
      openEmailPreviewModal("/api/mdes_cs_divergence/send", data.subject, data.body, { report_path: data.report_path }, () => loadReports());
    });
    statusEl.appendChild(sendBtn);
    loadMdesCsDivergence();
    loadReports();
  });
});

// ---------------------------------------------------------------------------
// Reports history (step 5)
// ---------------------------------------------------------------------------

function formatBytes(n) {
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDate(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleString("fr-FR");
}

async function loadReports() {
  const el = document.getElementById("reports-content");
  try {
    const res = await fetch("/api/reports");
    const data = await res.json();
    if (!res.ok) {
      el.className = "error";
      el.textContent = data.error || "Erreur inconnue.";
      return;
    }
    renderReports(data.reports, el);
  } catch (e) {
    el.className = "error";
    el.textContent = "Impossible de contacter le serveur (" + e.message + ").";
  }
}

const REPORTS_PAGE_SIZE = 8;

function renderReports(reports, el) {
  el.className = "";
  if (!reports.length) {
    el.innerHTML = `<p class="no-match-note">Aucun rapport généré pour l'instant.</p>`;
    return;
  }

  el.innerHTML = "";

  const list = document.createElement("div");
  list.className = "report-list";
  el.appendChild(list);

  let shownCount = 0;

  function appendRow(r) {
    const isExcel = r.name.toLowerCase().endsWith(".xlsx");
    const row = document.createElement("div");
    row.className = "report-row";
    row.innerHTML = `
      <div class="report-info">
        <div class="report-name">${isExcel ? "📊 " : ""}${r.name}</div>
        <div class="report-meta">${formatDate(r.modified_at)} — ${formatBytes(r.size_bytes)}</div>
      </div>
      <div class="report-actions">
        ${isExcel ? "" : '<button type="button" class="view-btn">Voir</button>'}
        <a href="/reports/${encodeURIComponent(r.name)}" download>Télécharger</a>
      </div>
    `;
    if (!isExcel) {
      row.querySelector(".view-btn").addEventListener("click", () => openReportModal(r.name));
    }
    list.appendChild(row);
  }

  function showNextPage() {
    const nextBatch = reports.slice(shownCount, shownCount + REPORTS_PAGE_SIZE);
    nextBatch.forEach(appendRow);
    shownCount += nextBatch.length;

    const existingBtn = el.querySelector(".show-more-btn");
    if (existingBtn) existingBtn.remove();

    if (shownCount < reports.length) {
      const moreBtn = document.createElement("button");
      moreBtn.type = "button";
      moreBtn.className = "action-btn show-more-btn";
      moreBtn.textContent = `Voir plus (${reports.length - shownCount} restant(s))`;
      moreBtn.addEventListener("click", showNextPage);
      el.appendChild(moreBtn);
    }
  }

  showNextPage();
}

async function openReportModal(name) {
  modalTitle.textContent = name;
  modalBody.innerHTML = "<p class=\"no-match-note\">Chargement…</p>";
  modalBody.classList.add("report-view");
  modalOverlay.classList.remove("hidden");

  try {
    const res = await fetch(`/reports/${encodeURIComponent(name)}`);
    const text = await res.text();
    if (!res.ok) {
      modalBody.innerHTML = `<p class="error">Impossible de charger ce fichier.</p>`;
      return;
    }
    const pre = document.createElement("pre");
    pre.className = "report-content-pre";
    pre.textContent = text;
    modalBody.innerHTML = "";
    modalBody.appendChild(pre);
  } catch (e) {
    modalBody.innerHTML = `<p class="error">Erreur réseau : ${e.message}</p>`;
  }
}

loadPhase1();
loadPhase2();
loadMdesCsDivergence();
loadMdesCsPrereleases();
loadMdesCsMapping();
loadReports();
