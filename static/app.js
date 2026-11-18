const state = {
  view: "tenders",
  limit: 30,
  offset: 0,
  total: 0,
  selectedCpvs: [],
  selectedSources: [],
  selectedStatuses: [],
  savedFilters: [],
  sources: [],
};

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function formatMoney(amount, currency = "EUR") {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) {
    return "No especificado";
  }
  const num = Number(amount);
  const sign = num < 0 ? "-" : "";
  const [intPart, decPart] = Math.abs(num).toFixed(2).split(".");
  const groupedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const symbol = currency === "EUR" || !currency ? "€" : currency;
  return `${sign}${groupedInt},${decPart} ${symbol}`;
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return isoStr;
  return d.toLocaleDateString("es-ES", { year: "numeric", month: "short", day: "2-digit" });
}

function formatDateTime(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return isoStr;
  return d.toLocaleString("es-ES", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function todayLocalIso() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let msg = `Error HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      if (err.detail) {
        msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      }
    } catch (_) {}
    throw new Error(msg);
  }
  return resp.json();
}

function renderMultiSelect(btnId, menuId, options, selectedArr, emptyLabel, onChange) {
  const btn = $(btnId);
  const menu = $(menuId);

  const updateLabel = () => {
    if (!selectedArr.length) {
      btn.textContent = emptyLabel;
    } else if (selectedArr.length === 1) {
      const found = options.find((o) => o.value === selectedArr[0]);
      btn.textContent = found ? found.label : selectedArr[0];
    } else {
      btn.textContent = `${selectedArr.length} seleccionados`;
    }
  };

  menu.innerHTML = "";
  options.forEach((opt) => {
    const lbl = document.createElement("label");
    lbl.className = "multi-select-opt";
    const checked = selectedArr.includes(opt.value);
    lbl.innerHTML = `
      <input type="checkbox" value="${escapeHtml(opt.value)}" ${checked ? "checked" : ""} />
      <span>${escapeHtml(opt.label)}</span>
    `;
    lbl.querySelector("input").addEventListener("change", (e) => {
      const val = e.target.value;
      if (e.target.checked) {
        if (!selectedArr.includes(val)) selectedArr.push(val);
      } else {
        const idx = selectedArr.indexOf(val);
        if (idx !== -1) selectedArr.splice(idx, 1);
      }
      updateLabel();
      onChange();
    });
    menu.appendChild(lbl);
  });
  updateLabel();
}

function setupMultiSelectToggle(wrapId, btnId, menuId) {
  $(btnId).addEventListener("click", (e) => {
    e.stopPropagation();
    const isHidden = $(menuId).classList.contains("hidden");
    document.querySelectorAll(".multi-select-menu").forEach((m) => m.classList.add("hidden"));
    if (isHidden) $(menuId).classList.remove("hidden");
  });
  $(menuId).addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", (e) => {
    if (!$(wrapId).contains(e.target)) {
      $(menuId).classList.add("hidden");
    }
  });
}

function switchView(viewName) {
  state.view = viewName;
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.remove("active"));

  if (viewName === "sources") {
    $("tab-sources").classList.add("active");
    $("view-tenders").classList.add("hidden");
    $("view-sources").classList.remove("hidden");
    loadSources();
    return;
  }

  $("tab-tenders").classList.add("active");
  $("view-sources").classList.add("hidden");
  $("view-tenders").classList.remove("hidden");
  state.offset = 0;
  loadTenders();
}

async function loadCpvCatalog() {
  const catalog = await apiFetch("/api/cpv-catalog");
  const select = $("select-common-cpv");
  catalog.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item.code;
    opt.textContent = `${item.code}* — ${item.label}`;
    opt.dataset.label = item.label;
    select.appendChild(opt);
  });
}

function renderCpvChips() {
  const container = $("selected-cpv-chips");
  container.innerHTML = "";
  state.selectedCpvs.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "cpv-chip";
    const text = item.label ? `${item.code} (${item.label})` : item.code;
    chip.innerHTML = `
      <span>${escapeHtml(text)}</span>
      <button type="button" title="Quitar CPV" data-cpv="${escapeHtml(item.code)}">×</button>
    `;
    chip.querySelector("button").addEventListener("click", () => {
      state.selectedCpvs = state.selectedCpvs.filter((c) => c.code !== item.code);
      renderCpvChips();
      state.offset = 0;
      loadTenders();
    });
    container.appendChild(chip);
  });
}

function addCpvChip(rawCode, label = "") {
  const parts = String(rawCode)
    .split(",")
    .map((p) => p.replace(/\D/g, "").trim())
    .filter(Boolean);
  let changed = false;
  parts.forEach((code) => {
    if (!state.selectedCpvs.some((c) => c.code === code)) {
      state.selectedCpvs.push({ code, label });
      changed = true;
    }
  });
  if (changed) {
    renderCpvChips();
    state.offset = 0;
    loadTenders();
  }
}

function getCurrentFilterState() {
  return {
    q: $("filter-q").value.trim(),
    cpvs: state.selectedCpvs,
    sources: [...state.selectedSources],
    statuses: [...state.selectedStatuses],
    authority: $("filter-authority").value.trim(),
    only_favorites: $("filter-favorites").checked,
    date_from: $("filter-date-from").value,
    date_to: $("filter-date-to").value,
    min_budget: $("filter-min-budget").value.trim(),
    sort: $("filter-sort").value,
  };
}

function applyFilterState(filters) {
  $("filter-q").value = filters.q || "";
  state.selectedCpvs = Array.isArray(filters.cpvs) ? filters.cpvs : [];
  renderCpvChips();

  state.selectedSources.splice(
    0,
    state.selectedSources.length,
    ...(Array.isArray(filters.sources) ? filters.sources : filters.source ? [filters.source] : [])
  );
  state.selectedStatuses.splice(
    0,
    state.selectedStatuses.length,
    ...(Array.isArray(filters.statuses)
      ? filters.statuses
      : filters.status_mode
      ? [filters.status_mode]
      : [])
  );

  $("filter-authority").value = filters.authority || "";
  $("filter-favorites").checked = Boolean(filters.only_favorites);
  $("filter-date-from").value = filters.date_from || "";
  $("filter-date-to").value = filters.date_to || "";
  $("filter-min-budget").value = filters.min_budget || "";
  $("filter-sort").value = filters.sort || "published_desc";

  renderSourcesMultiSelect();
  loadStatuses().then(() => {
    state.offset = 0;
    loadTenders();
  });
}

async function loadSavedFilters() {
  state.savedFilters = await apiFetch("/api/saved-filters");
  const bar = $("saved-filters-bar");
  bar.innerHTML = "";
  if (!state.savedFilters.length) return;

  const label = document.createElement("span");
  label.className = "small-inline-label";
  label.textContent = "Guardados:";
  bar.appendChild(label);

  state.savedFilters.forEach((sf) => {
    const pill = document.createElement("span");
    pill.className = "saved-filter-pill";
    pill.innerHTML = `
      <span class="saved-filter-name">${escapeHtml(sf.name)}</span>
      <button type="button" class="saved-filter-del" title="Eliminar filtro">×</button>
    `;
    pill.querySelector(".saved-filter-name").addEventListener("click", () => {
      applyFilterState(sf.filters || {});
    });
    pill.querySelector(".saved-filter-del").addEventListener("click", async (e) => {
      e.stopPropagation();
      await apiFetch(`/api/saved-filters/${sf.id}`, { method: "DELETE" });
      await loadSavedFilters();
    });
    bar.appendChild(pill);
  });
}

function renderSourcesMultiSelect() {
  const opts = state.sources.map((s) => ({ value: s.id, label: s.name }));
  renderMultiSelect(
    "ms-sources-btn",
    "ms-sources-menu",
    opts,
    state.selectedSources,
    "Todas las fuentes",
    () => {
      state.offset = 0;
      loadTenders();
    }
  );
}

async function loadSources() {
  state.sources = await apiFetch("/api/sources");
  renderSourcesMultiSelect();

  const tbody = $("sources-tbody");
  tbody.innerHTML = "";
  state.sources.forEach((s) => {
    const run = s.last_run;
    const statusHtml = !run
      ? '<span class="muted">Sin sincronizar</span>'
      : run.status === "running"
      ? '<span class="pill-run">Sincronizando...</span>'
      : run.status === "ok"
      ? `<span class="pill-ok">OK</span> <span class="muted">${escapeHtml(run.message)}</span>`
      : `<span class="pill-err">Error</span> <span class="muted">${escapeHtml(run.message)}</span>`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(s.name)}</strong><br><span class="muted">${escapeHtml(s.region)}</span></td>
      <td>${escapeHtml(s.tier)}</td>
      <td>${escapeHtml(s.format)}</td>
      <td>${s.tender_count}</td>
      <td>${run ? formatDateTime(run.finished_at || run.started_at) : "—"}</td>
      <td>${statusHtml}</td>
      <td><button class="btn btn-secondary" data-sync-src="${escapeHtml(s.id)}">Sincronizar</button></td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll("button[data-sync-src]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const sid = e.target.dataset.syncSrc;
      await runSync([sid]);
    });
  });
}

async function loadStatuses() {
  const statuses = await apiFetch("/api/statuses");
  const opts = [
    { value: "deadline:open", label: "Abiertas (en plazo)" },
    { value: "deadline:closed", label: "Cerradas (vencidas / adjudicadas)" },
    ...statuses.map((st) => ({ value: `status:${st}`, label: st })),
  ];
  renderMultiSelect(
    "ms-statuses-btn",
    "ms-statuses-menu",
    opts,
    state.selectedStatuses,
    "Todos los estados",
    () => {
      state.offset = 0;
      loadTenders();
    }
  );
}

async function loadTenders() {
  const cpvCodes = state.selectedCpvs.map((c) => c.code);
  const typedCpv = $("filter-cpv-input").value.trim();
  if (typedCpv) {
    typedCpv
      .split(",")
      .map((p) => p.replace(/\D/g, "").trim())
      .filter(Boolean)
      .forEach((c) => {
        if (!cpvCodes.includes(c)) cpvCodes.push(c);
      });
  }

  const deadlineStates = [];
  const exactStatuses = [];
  state.selectedStatuses.forEach((val) => {
    if (val.startsWith("deadline:")) {
      deadlineStates.push(val.slice("deadline:".length));
    } else if (val.startsWith("status:")) {
      exactStatuses.push(val.slice("status:".length));
    }
  });

  const params = new URLSearchParams({
    q: $("filter-q").value.trim(),
    cpv: cpvCodes.join(","),
    source: state.selectedSources.join(","),
    status: exactStatuses.join(","),
    deadline_state: deadlineStates.join(","),
    authority: $("filter-authority").value.trim(),
    only_favorites: String($("filter-favorites").checked),
    sort: $("filter-sort").value || "published_desc",
    limit: String(state.limit),
    offset: String(state.offset),
  });

  const dateFrom = $("filter-date-from").value;
  if (dateFrom) params.set("date_from", dateFrom);
  const dateTo = $("filter-date-to").value;
  if (dateTo) params.set("date_to", dateTo);
  const minBudget = $("filter-min-budget").value.trim();
  if (minBudget) params.set("min_budget", minBudget);

  const data = await apiFetch(`/api/tenders?${params.toString()}`);
  state.total = data.total;
  renderTenders(data.items, data.total);
}

async function toggleFavorite(tenderId, btnEl) {
  const res = await apiFetch(`/api/tenders/${tenderId}/favorite`, { method: "POST" });
  if (btnEl) {
    btnEl.classList.toggle("active", res.is_favorite);
    btnEl.textContent = res.is_favorite ? "★" : "☆";
    btnEl.title = res.is_favorite ? "Quitar de favoritas" : "Marcar como favorita";
  }
  if ($("filter-favorites").checked && !res.is_favorite) {
    loadTenders();
  }
}

function renderTenders(items, total) {
  const list = $("tenders-list");
  const currentPage = Math.floor(state.offset / state.limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / state.limit));

  $("results-summary").textContent = `${total} licitación${total === 1 ? "" : "es"} encontrada${total === 1 ? "" : "s"}`;
  $("page-info").textContent = `Página ${currentPage} de ${totalPages}`;
  $("btn-prev").disabled = state.offset <= 0;
  $("btn-next").disabled = state.offset + state.limit >= total;

  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML =
      '<div class="empty-state">No hay licitaciones para estos filtros. Ajusta los criterios o pulsa «Sincronizar fuentes».</div>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "tender-card";
    const cpvsHtml = (item.cpvs || [])
      .slice(0, 6)
      .map((c) => `<span class="cpv-tag">${escapeHtml(c)}</span>`)
      .join("");

    const budgetVal = item.budget_amount ?? item.estimated_value;
    const budgetBadge =
      budgetVal !== null && budgetVal !== undefined
        ? `<span class="badge badge-budget">${escapeHtml(formatMoney(budgetVal, item.currency))}</span>`
        : '<span class="badge badge-status">Importe n/d</span>';
    const directLink = item.url
      ? `<a class="btn-link-ext" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">Ver anuncio ↗</a>`
      : "";

    const favActive = item.is_favorite ? " active" : "";
    const favSymbol = item.is_favorite ? "★" : "☆";
    const authorityText = item.contracting_authority || "No indicado";
    const authorityHtml = item.contracting_authority
      ? `<button type="button" class="authority-link" data-authority="${escapeHtml(item.contracting_authority)}" title="Filtrar por este órgano">${escapeHtml(authorityText)}</button>`
      : escapeHtml(authorityText);

    card.innerHTML = `
      <div class="tender-top">
        <div class="tender-badges">
          <button type="button" class="btn-fav${favActive}" title="${item.is_favorite ? "Quitar de favoritas" : "Marcar como favorita"}">${favSymbol}</button>
          <span class="badge badge-source">${escapeHtml(item.source)}</span>
          ${item.status ? `<span class="badge badge-status">${escapeHtml(item.status)}</span>` : ""}
        </div>
        <div class="tender-right">
          ${budgetBadge}
          <span class="muted">Pub: ${formatDate(item.published_at)}</span>
          ${directLink}
        </div>
      </div>
      <h3 class="tender-title">${escapeHtml(item.title)}</h3>
      <div class="tender-meta">
        <span><strong>Órgano:</strong> ${authorityHtml}</span>
        <span><strong>Expediente:</strong> ${escapeHtml(item.expediente || "—")}</span>
        <span><strong>Plazo:</strong> ${formatDate(item.deadline_at)}</span>
      </div>
      ${cpvsHtml ? `<div class="cpv-tags">${cpvsHtml}</div>` : ""}
    `;

    card.querySelector(".btn-fav").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorite(item.id, e.currentTarget);
    });

    const authBtn = card.querySelector(".authority-link");
    if (authBtn) {
      authBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        $("filter-authority").value = authBtn.dataset.authority;
        state.offset = 0;
        loadTenders();
      });
    }

    card.addEventListener("click", () => openDetail(item.id));
    list.appendChild(card);
  });
}

async function openDetail(tenderId) {
  const item = await apiFetch(`/api/tenders/${tenderId}`);
  $("modal-source").textContent = `${item.source} (${item.region || "España"})`;
  $("modal-status").textContent = item.status || "Sin estado";
  $("modal-title").textContent = item.title;

  $("modal-meta").innerHTML = `
    <div><strong>Expediente:</strong> ${escapeHtml(item.expediente)}</div>
    <div><strong>Órgano:</strong> ${escapeHtml(item.contracting_authority || "No indicado")}</div>
    <div><strong>Presupuesto:</strong> ${formatMoney(item.budget_amount, item.currency)}</div>
    <div><strong>Valor estimado:</strong> ${formatMoney(item.estimated_value, item.currency)}</div>
    <div><strong>Publicación:</strong> ${formatDate(item.published_at)}</div>
    <div><strong>Fecha límite:</strong> ${formatDate(item.deadline_at)}</div>
    <div><strong>Tipo contrato:</strong> ${escapeHtml(item.contract_type || "—")}</div>
    <div><strong>Procedimiento:</strong> ${escapeHtml(item.procedure || "—")}</div>
  `;

  $("modal-summary").textContent = item.summary || "Sin descripción adicional en el feed.";
  $("modal-cpvs").innerHTML = (item.cpvs || []).length
    ? item.cpvs.map((c) => `<span class="cpv-tag">${escapeHtml(c)}</span>`).join("")
    : '<span class="muted">Sin CPV especificado</span>';

  const linkEl = $("modal-url");
  if (item.url) {
    linkEl.href = item.url;
    linkEl.classList.remove("hidden");
  } else {
    linkEl.classList.add("hidden");
  }

  $("detail-modal").classList.remove("hidden");
}

let syncPollTimer = null;

function stopSyncPolling() {
  if (syncPollTimer) {
    clearInterval(syncPollTimer);
    syncPollTimer = null;
  }
}

async function pollSyncProgress() {
  await loadSources();
  const runningCount = state.sources.filter((s) => s.last_run && s.last_run.status === "running").length;
  if (runningCount > 0) {
    $("sync-status-text").textContent = `Sincronizando (${runningCount} en curso)...`;
    return;
  }
  stopSyncPolling();
  $("btn-sync-all").disabled = false;
  const okCount = state.sources.filter((s) => s.last_run && s.last_run.status === "ok").length;
  $("sync-status-text").textContent = `Listo (${okCount}/${state.sources.length} OK)`;
  await loadStatuses();
  await loadTenders();
}

async function runSync(sources = null) {
  const btn = $("btn-sync-all");
  btn.disabled = true;
  const dateFrom = $("sync-date-from").value || todayLocalIso();
  const dateTo = $("sync-date-to").value || todayLocalIso();
  $("sync-status-text").textContent = `Sincronizando (${dateFrom} a ${dateTo})...`;
  try {
    await apiFetch("/api/sync", {
      method: "POST",
      body: JSON.stringify({
        sources,
        max_pages: 200,
        date_from: dateFrom,
        date_to: dateTo,
      }),
    });
    await loadSources();
    stopSyncPolling();
    syncPollTimer = setInterval(() => {
      pollSyncProgress().catch(() => stopSyncPolling());
    }, 2500);
  } catch (err) {
    $("sync-status-text").textContent = `Error: ${err.message}`;
    btn.disabled = false;
  }
}

function wireEvents() {
  setupMultiSelectToggle("ms-sources", "ms-sources-btn", "ms-sources-menu");
  setupMultiSelectToggle("ms-statuses", "ms-statuses-btn", "ms-statuses-menu");

  $("tab-tenders").addEventListener("click", () => switchView("tenders"));
  $("tab-sources").addEventListener("click", () => switchView("sources"));

  $("btn-sync-all").addEventListener("click", () => runSync(null));

  $("btn-shutdown").addEventListener("click", () => {
    $("confirm-modal").classList.remove("hidden");
  });

  $("btn-cancel-confirm").addEventListener("click", () => {
    $("confirm-modal").classList.add("hidden");
  });

  $("btn-cancel-exit").addEventListener("click", () => {
    $("confirm-modal").classList.add("hidden");
  });

  $("confirm-modal").addEventListener("click", (e) => {
    if (e.target.id === "confirm-modal") {
      $("confirm-modal").classList.add("hidden");
    }
  });

  $("btn-confirm-exit").addEventListener("click", async () => {
    $("confirm-modal").classList.add("hidden");
    try {
      await apiFetch("/api/shutdown", { method: "POST" });
    } catch (_) {}
    document.body.innerHTML = `
      <div class="shutdown-screen">
        <div class="card" style="max-width:440px;text-align:center;padding:2rem">
          <h2 style="margin:0 0 0.5rem">Cerrando LicitAll...</h2>
          <p class="muted">El servidor Python se ha detenido correctamente. Esta ventana se cerrará en 2 segundos.</p>
        </div>
      </div>
    `;
    setTimeout(() => {
      window.open("", "_self");
      window.close();
      const p = document.querySelector(".shutdown-screen p");
      if (p) {
        p.textContent = "El servidor Python se ha detenido. Ya puedes cerrar esta pestaña (Ctrl + W).";
      }
    }, 2000);
  });

  $("select-common-cpv").addEventListener("change", (e) => {
    const code = e.target.value;
    if (!code) return;
    const label = e.target.selectedOptions[0]?.dataset.label || "";
    addCpvChip(code, label);
    e.target.value = "";
  });

  $("btn-add-cpv-chip").addEventListener("click", () => {
    const val = $("filter-cpv-input").value.trim();
    if (!val) return;
    addCpvChip(val);
    $("filter-cpv-input").value = "";
  });

  $("filter-cpv-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      $("btn-add-cpv-chip").click();
    }
  });

  $("form-search").addEventListener("submit", (e) => {
    e.preventDefault();
    state.offset = 0;
    loadTenders();
  });

  $("filter-favorites").addEventListener("change", () => {
    state.offset = 0;
    loadTenders();
  });

  $("filter-date-from").addEventListener("change", () => {
    state.offset = 0;
    loadTenders();
  });

  $("filter-date-to").addEventListener("change", () => {
    state.offset = 0;
    loadTenders();
  });

  $("filter-sort").addEventListener("change", () => {
    state.offset = 0;
    loadTenders();
  });

  $("btn-open-save-filter").addEventListener("click", () => {
    $("input-save-filter-name").value = "";
    $("save-filter-modal").classList.remove("hidden");
    $("input-save-filter-name").focus();
  });

  $("btn-close-save-modal").addEventListener("click", () => {
    $("save-filter-modal").classList.add("hidden");
  });

  $("btn-cancel-save-filter").addEventListener("click", () => {
    $("save-filter-modal").classList.add("hidden");
  });

  $("form-save-filter").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("input-save-filter-name").value.trim();
    if (!name) return;
    await apiFetch("/api/saved-filters", {
      method: "POST",
      body: JSON.stringify({ name, filters: getCurrentFilterState() }),
    });
    $("save-filter-modal").classList.add("hidden");
    await loadSavedFilters();
  });

  $("btn-clear-filters").addEventListener("click", () => {
    $("filter-q").value = "";
    $("filter-cpv-input").value = "";
    state.selectedCpvs = [];
    renderCpvChips();
    state.selectedSources.splice(0, state.selectedSources.length);
    state.selectedStatuses.splice(0, state.selectedStatuses.length);
    renderSourcesMultiSelect();
    loadStatuses();
    $("filter-authority").value = "";
    $("filter-favorites").checked = false;
    $("filter-date-from").value = "";
    $("filter-date-to").value = "";
    $("filter-min-budget").value = "";
    $("filter-sort").value = "published_desc";
    state.offset = 0;
    loadTenders();
  });

  $("btn-prev").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    loadTenders();
  });

  $("btn-next").addEventListener("click", () => {
    state.offset += state.limit;
    loadTenders();
  });

  $("btn-close-modal").addEventListener("click", () => {
    $("detail-modal").classList.add("hidden");
  });

  $("detail-modal").addEventListener("click", (e) => {
    if (e.target.id === "detail-modal") {
      $("detail-modal").classList.add("hidden");
    }
  });
}

async function init() {
  const today = todayLocalIso();
  $("sync-date-from").value = today;
  $("sync-date-to").value = today;
  wireEvents();
  await Promise.all([loadCpvCatalog(), loadSavedFilters(), loadSources(), loadStatuses()]);
  await loadTenders();
}

init();
