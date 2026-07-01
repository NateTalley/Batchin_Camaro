// Cross-browser API shim: Firefox exposes the promise-based WebExtension API as
// `browser`; Chrome MV3 exposes it as `chrome`. Bind whichever exists to `api`.
// We must NOT reuse the name `chrome` — it's a read-only global in Chrome, and
// redeclaring it with `const` throws at load time.
const api = globalThis.browser ?? globalThis.chrome;

const ITEM_ID_RE = /archive\.org\/details\/([^/?#]+)/;

function extractItemId(url) {
  const m = url.match(ITEM_ID_RE);
  return m ? m[1] : null;
}

function cleanTitle(raw) {
  return raw
    .replace(/ [:\-] Free Download, Borrow.*$/i, "")
    .replace(/ [:\-] Internet Archive$/i, "")
    .replace(/ : [^:]+: Internet Archive$/i, "")
    .trim();
}

function esc(str) {
  return str
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── State ─────────────────────────────────────────────────────────────────────

let archiveTabs = [];
let pollTimer   = null;
let agentPollTimer = null;
let running     = false;

// ── Auth keys ─────────────────────────────────────────────────────────────────

async function loadKeys() {
  const { iaAccessKey = "", iaSecretKey = "" } =
    await api.storage.local.get(["iaAccessKey", "iaSecretKey"]);
  document.getElementById("access-key").value = iaAccessKey;
  document.getElementById("secret-key").value = iaSecretKey;
  document.getElementById("settings-btn")
    .classList.toggle("has-keys", !!(iaAccessKey && iaSecretKey));
}

async function saveKeys() {
  const accessKey = document.getElementById("access-key").value.trim();
  const secretKey = document.getElementById("secret-key").value.trim();
  await api.storage.local.set({ iaAccessKey: accessKey, iaSecretKey: secretKey });
  document.getElementById("settings-btn")
    .classList.toggle("has-keys", !!(accessKey && secretKey));
  const msg = document.getElementById("keys-saved-msg");
  msg.textContent = accessKey && secretKey ? "Keys saved" : "Keys cleared";
  msg.classList.add("visible");
  setTimeout(() => msg.classList.remove("visible"), 2000);
}

async function clearKeys() {
  document.getElementById("access-key").value = "";
  document.getElementById("secret-key").value = "";
  await saveKeys();
}

async function getAuthHeader() {
  const { iaAccessKey = "", iaSecretKey = "" } =
    await api.storage.local.get(["iaAccessKey", "iaSecretKey"]);
  if (iaAccessKey && iaSecretKey) return `LOW ${iaAccessKey}:${iaSecretKey}`;
  return null;
}

// ── Download settings (persisted) ─────────────────────────────────────────────

const SETTING_KEYS = [
  "wantExtra", "wantZip", "wantOneFolder",
  "exportTxt", "exportCsv", "exportJson", "sizeLimitGb"
];

async function loadSettings() {
  const prefs = await api.storage.local.get(SETTING_KEYS);
  document.getElementById("want-extra").checked      = prefs.wantExtra      ?? false;
  document.getElementById("want-zip").checked        = prefs.wantZip        ?? false;
  document.getElementById("want-one-folder").checked = prefs.wantOneFolder  ?? false;
  document.getElementById("export-txt").checked      = prefs.exportTxt      ?? false;
  document.getElementById("export-csv").checked      = prefs.exportCsv      ?? false;
  document.getElementById("export-json").checked     = prefs.exportJson     ?? false;
  document.getElementById("size-limit").value        = prefs.sizeLimitGb    ?? 0;
}

async function saveSettings() {
  await api.storage.local.set({
    wantExtra:    document.getElementById("want-extra").checked,
    wantZip:      document.getElementById("want-zip").checked,
    wantOneFolder:document.getElementById("want-one-folder").checked,
    exportTxt:    document.getElementById("export-txt").checked,
    exportCsv:    document.getElementById("export-csv").checked,
    exportJson:   document.getElementById("export-json").checked,
    sizeLimitGb:  parseFloat(document.getElementById("size-limit").value) || 0,
  });
}

function collectOptions() {
  return {
    wantText:     document.getElementById("want-text").checked,
    wantPdf:      document.getElementById("want-pdf").checked,
    wantExtra:    document.getElementById("want-extra").checked,
    wantZip:      document.getElementById("want-zip").checked,
    wantOneFolder:document.getElementById("want-one-folder").checked,
    exportTxt:    document.getElementById("export-txt").checked,
    exportCsv:    document.getElementById("export-csv").checked,
    exportJson:   document.getElementById("export-json").checked,
    sizeLimitGb:  parseFloat(document.getElementById("size-limit").value) || 0,
  };
}

// ── CSV export ──────────────────────────────────────────────────────────────

function toCsv(header, rows) {
  const q = v => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [header, ...rows].map(r => r.map(q).join(",")).join("\r\n") + "\r\n";
}

async function downloadCsv(filename, header, rows) {
  const url = `data:text/csv;charset=utf-8,${encodeURIComponent(toCsv(header, rows))}`;
  await api.downloads.download({
    url,
    filename: `Archive Downloads/${filename}`,
    conflictAction: "uniquify",
    saveAs: false
  });
}

// Export the URLs of every open archive.org tab to a CSV.
async function exportTabUrls() {
  if (!archiveTabs.length) return;
  const rows = archiveTabs.map(t => [t.id, t.title, t.url]);
  await downloadCsv("archive-tab-urls.csv", ["id", "title", "url"], rows);
  setStatus(`Exported ${rows.length} tab URL${rows.length !== 1 ? "s" : ""} to CSV.`, "success");
}

// Items that yielded no download: borrow-only (restricted), no matching files,
// or errored. Used to show / populate the "Export Locked List" button.
function lockedItems(items) {
  return Object.entries(items || {})
    .filter(([, st]) => st.status === "restricted" || st.status === "no_files" || st.status === "error")
    .map(([id, st]) => ({ id, title: st.title || "", status: st.status }));
}

function updateLockedExportBtn(items) {
  const locked = lockedItems(items).length > 0;
  document.getElementById("export-locked-btn").hidden = !locked;
  const batchBtn = document.getElementById("batch-export-locked-btn");
  if (batchBtn) batchBtn.hidden = !locked;
}

// Export the locked / unavailable items from the last run, with a details URL
// so the user can track them down by other means later.
async function exportLockedList() {
  const { downloadStatus: s = {} } = await api.storage.local.get("downloadStatus");
  const locked = lockedItems(s.items);
  if (!locked.length) return;
  const rows = locked.map(u => [u.id, u.title, u.status, `https://archive.org/details/${u.id}`]);
  await downloadCsv("locked-items.csv", ["id", "title", "status", "url"], rows);
  setStatus(`Exported ${rows.length} locked item${rows.length !== 1 ? "s" : ""} to CSV.`, "success");
}

// ── Tab discovery ─────────────────────────────────────────────────────────────

async function loadTabs() {
  const tabs = await api.tabs.query({ url: "*://*.archive.org/details/*" });
  archiveTabs = tabs
    .map(t => ({
      id: extractItemId(t.url), title: cleanTitle(t.title || t.url),
      tabId: t.id, url: t.url, selected: true
    }))
    .filter(t => t.id !== null);
  renderList();
  refreshUI();
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderList() {
  const list  = document.getElementById("tab-list");
  const empty = document.getElementById("empty-state");
  const count = document.getElementById("tab-count");

  if (archiveTabs.length === 0) {
    list.style.display  = "none";
    empty.style.display = "block";
    count.textContent   = "No archive.org/details/ tabs open";
    return;
  }
  empty.style.display = "none";
  list.style.display  = "block";
  count.textContent   =
    `Found ${archiveTabs.length} archive.org tab${archiveTabs.length !== 1 ? "s" : ""}`;

  list.innerHTML = "";
  for (const item of archiveTabs) {
    const li = document.createElement("li");
    li.className = "tab-row";
    li.dataset.id = item.id;
    li.innerHTML = `
      <label class="tab-label">
        <input type="checkbox" class="tab-checkbox" data-id="${esc(item.id)}"
               ${item.selected ? "checked" : ""}>
        <span class="tab-info">
          <span class="item-id">${esc(item.id)}</span>
          <span class="item-title">${esc(item.title)}</span>
        </span>
      </label>
      <span class="tab-status" data-status-id="${esc(item.id)}"></span>`;
    list.appendChild(li);
  }

  list.querySelectorAll(".tab-checkbox").forEach(cb => {
    cb.addEventListener("change", () => {
      const t = archiveTabs.find(x => x.id === cb.dataset.id);
      if (t) t.selected = cb.checked;
      refreshUI();
    });
  });
}

function refreshUI() {
  const selected = archiveTabs.filter(t => t.selected);
  const opts     = collectOptions();
  const hasFormat = opts.wantText || opts.wantPdf || opts.wantExtra || opts.wantZip;
  const btn   = document.getElementById("download-btn");
  const label = document.getElementById("btn-label");

  btn.disabled = running || selected.length === 0 || !hasFormat;
  document.getElementById("export-urls-btn").disabled = running || archiveTabs.length === 0;
  label.textContent = selected.length > 0
    ? `Download & Close ${selected.length} Tab${selected.length !== 1 ? "s" : ""}`
    : "Download & Close Tabs";
}

function setStatus(msg, type = "info") {
  const el = document.getElementById("status-msg");
  if (!el) return;
  el.textContent = msg;
  el.className = `status-msg status-${type}`;
}

function setRunning(state) {
  running = state;
  document.getElementById("stop-btn").hidden      = !state;
  document.getElementById("controls").classList.toggle("disabled", state);
  document.getElementById("download-btn").disabled = state;
}

// ── Download trigger ──────────────────────────────────────────────────────────

async function startDownloads() {
  const selected = archiveTabs.filter(t => t.selected);
  const opts     = collectOptions();
  const hasFormat = opts.wantText || opts.wantPdf || opts.wantExtra || opts.wantZip;
  if (!selected.length || !hasFormat) return;

  setRunning(true);
  setStatus("Starting…");
  document.getElementById("export-locked-btn").hidden = true;
  await saveSettings();
  await api.storage.local.remove("downloadStatus");

  const authHeader = await getAuthHeader();

  await api.runtime.sendMessage({
    action:  "START_DOWNLOADS",
    items:   selected.map(t => ({ id: t.id, title: t.title, tabId: t.tabId })),
    options: { ...opts, authHeader }
  });

  pollTimer = setInterval(pollStatus, 600);
}

async function stopDownloads() {
  const { downloadStatus: s = {} } = await api.storage.local.get("downloadStatus");
  await api.storage.local.set({ downloadStatus: { ...s, stopRequested: true } });
  document.getElementById("stop-btn").hidden = true;
  setStatus("Stopping after current item…", "info");
}

// ── Status polling ────────────────────────────────────────────────────────────

async function pollStatus() {
  const { downloadStatus: s } = await api.storage.local.get("downloadStatus");
  if (!s) return;

  for (const [itemId, st] of Object.entries(s.items || {})) {
    const el = document.querySelector(`[data-status-id="${CSS.escape(itemId)}"]`);
    if (!el) continue;
    switch (st.status) {
      case "pending":     el.textContent = "…";        el.title = "Queued";           el.className = "tab-status"; break;
      case "fetching":    el.textContent = "🔍";       el.title = "Fetching metadata"; el.className = "tab-status"; break;
      case "downloading":
        el.textContent = `⬇ ${st.filesDownloaded ?? 0}/${st.filesCount ?? "?"}`;
        el.title = st.skippedSize ? `${st.skippedSize} file(s) skipped (size limit)` : "Downloading";
        el.className = "tab-status"; break;
      case "done":
        el.textContent = "✓ done"; el.className = "tab-status status-done";
        el.title = `${st.filesDownloaded ?? 0} file(s) saved`
          + (st.skippedSize ? `, ${st.skippedSize} skipped` : "")
          + (st.unavailable ? `, ${st.unavailable} unavailable` : ""); break;
      case "restricted":
        el.textContent = "🔒 locked"; el.className = "tab-status status-error";
        el.title = "Borrow-only / access-restricted item — files require you to be logged in and have it borrowed on archive.org"; break;
      case "no_files":    el.textContent = "— none";   el.title = "No matching files"; el.className = "tab-status"; break;
      case "stopped":     el.textContent = "⏹ stopped"; el.title = "Stopped";         el.className = "tab-status"; break;
      case "error":       el.textContent = "✗ error";  el.title = st.error || "Error"; el.className = "tab-status status-error"; break;
    }
  }

  if (s.total > 0) setStatus(`${s.completed ?? 0} / ${s.total} items processed…`);

  if (s.done) {
    clearInterval(pollTimer);
    pollTimer = null;
    setRunning(false);
    updateLockedExportBtn(s.items);

    const items   = Object.values(s.items || {});
    const errs    = items.filter(x => x.status === "error").length;
    const locked  = items.filter(x => x.status === "restricted").length;
    const stopped = s.stopRequested;
    const tail = locked ? ` ${locked} item(s) locked (borrow-only).` : "";
    const msg = stopped
      ? `Stopped. ${s.completed ?? 0}/${s.total} items done.${tail}`
      : errs > 0
        ? `Done — ${errs} error(s).${tail} Files in Downloads/Archive Downloads/.`
        : `All done! Files saved to Downloads/Archive Downloads/.${tail}`;
    setStatus(msg, errs > 0 ? "error" : (locked ? "info" : "success"));

    setTimeout(loadTabs, 800);
  }
}

// ── Tab navigation ────────────────────────────────────────────────────────────

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.classList.toggle("active", panel.id === `panel-${tabId}`);
  });
  api.storage.local.set({ activeTab: tabId });
}

// ── Agent chat ──────────────────────────────────────────────────────────────

function renderAgentChat(transcript) {
  const el = document.getElementById("agent-chat");
  if (!el) return;
  el.innerHTML = "";
  const text = transcript || "Ask me to search archive.org or download items.\n";
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const div = document.createElement("div");
    if (line.startsWith("You:")) div.className = "line-user";
    else if (line.startsWith("Assistant:")) div.className = "line-assistant";
    else if (line.startsWith("  [tool]")) div.className = "line-tool";
    else if (line.startsWith("Error:")) div.className = "line-error";
    else div.className = "line-assistant";
    div.textContent = line;
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

function setAgentStatus(msg, type = "") {
  const el = document.getElementById("agent-status");
  if (!el) return;
  el.textContent = msg;
  el.className = "agent-status" + (type ? ` ${type}` : "");
}

async function refreshOllamaModels() {
  const baseUrl = document.getElementById("ollama-url").value.trim() || "http://127.0.0.1:11434";
  const resp = await api.runtime.sendMessage({ action: "LIST_OLLAMA_MODELS", baseUrl });
  if (!resp?.ok) {
    setAgentStatus(resp?.error || "Cannot reach Ollama", "error");
    return;
  }
  const sel = document.getElementById("ollama-model");
  sel.innerHTML = "";
  for (const m of resp.models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    sel.appendChild(opt);
  }
  if (resp.models.length) {
    sel.value = resp.models[0];
    setAgentStatus(`Connected — ${resp.models.length} model(s) available`, "ok");
  } else {
    setAgentStatus("Ollama reachable but no models found. Run: ollama pull llama3.1", "error");
  }
  await api.storage.local.set({ ollamaUrl: baseUrl, ollamaModel: sel.value });
}

async function sendAgentMessage(text) {
  const message = (text || document.getElementById("agent-input").value || "").trim();
  if (!message) return;
  document.getElementById("agent-input").value = "";
  const baseUrl = document.getElementById("ollama-url").value.trim() || "http://127.0.0.1:11434";
  const model = document.getElementById("ollama-model").value || "llama3.1";
  setAgentStatus("Thinking…");
  document.getElementById("agent-send-btn").disabled = true;

  const { agentStatus: prev = {} } = await api.storage.local.get("agentStatus");
  const transcript = (prev.transcript || "") + `\nYou: ${message}\n`;
  renderAgentChat(transcript);

  await api.runtime.sendMessage({ action: "AGENT_CHAT", message, baseUrl, model });
  if (!agentPollTimer) agentPollTimer = setInterval(pollAgentStatus, 500);
}

async function pollAgentStatus() {
  const { agentStatus: s = {} } = await api.storage.local.get("agentStatus");
  if (s.transcript) renderAgentChat(s.transcript);
  if (s.running) {
    setAgentStatus("Running tools…");
    return;
  }
  if (s.error) setAgentStatus(s.error, "error");
  else if (s.done) setAgentStatus("Ready", "ok");

  if (s.done || s.error) {
    clearInterval(agentPollTimer);
    agentPollTimer = null;
    document.getElementById("agent-send-btn").disabled = false;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  await loadTabs();
  await loadKeys();
  await loadSettings();

  const { activeTab = "download", ollamaUrl, ollamaModel } = await api.storage.local.get([
    "activeTab", "ollamaUrl", "ollamaModel"
  ]);
  if (ollamaUrl) document.getElementById("ollama-url").value = ollamaUrl;
  if (ollamaModel) document.getElementById("ollama-model").value = ollamaModel;
  switchTab(activeTab);

  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("refresh-models-btn").addEventListener("click", refreshOllamaModels);
  document.getElementById("agent-send-btn").addEventListener("click", () => sendAgentMessage());
  document.getElementById("agent-input").addEventListener("keydown", e => {
    if (e.key === "Enter") sendAgentMessage();
  });
  document.querySelectorAll(".example-prompt").forEach(btn => {
    btn.addEventListener("click", () => sendAgentMessage(btn.dataset.prompt));
  });

  const { agentStatus: as = {} } = await api.storage.local.get("agentStatus");
  if (as.transcript) renderAgentChat(as.transcript);
  if (as.running) {
    document.getElementById("agent-send-btn").disabled = true;
    agentPollTimer = setInterval(pollAgentStatus, 500);
  }

  document.getElementById("batch-export-urls-btn").addEventListener("click", exportTabUrls);
  document.getElementById("batch-export-locked-btn").addEventListener("click", exportLockedList);

  // Settings panel toggle
  document.getElementById("settings-btn").addEventListener("click", () => {
    const panel = document.getElementById("settings-panel");
    panel.hidden = !panel.hidden;
  });
  document.getElementById("save-keys-btn").addEventListener("click", saveKeys);
  document.getElementById("clear-keys-btn").addEventListener("click", clearKeys);

  // Auto-save settings on change
  ["want-extra","want-zip","want-one-folder","export-txt","export-csv","export-json","size-limit"]
    .forEach(id => document.getElementById(id).addEventListener("change", saveSettings));

  document.getElementById("download-btn").addEventListener("click", startDownloads);
  document.getElementById("stop-btn").addEventListener("click", stopDownloads);
  document.getElementById("export-urls-btn").addEventListener("click", exportTabUrls);
  document.getElementById("export-locked-btn").addEventListener("click", exportLockedList);
  document.getElementById("want-text").addEventListener("change", refreshUI);
  document.getElementById("want-pdf").addEventListener("change", refreshUI);
  document.getElementById("refresh-btn").addEventListener("click", loadTabs);

  document.getElementById("select-all").addEventListener("click", () => {
    archiveTabs.forEach(t => (t.selected = true));
    document.querySelectorAll(".tab-checkbox").forEach(cb => (cb.checked = true));
    refreshUI();
  });
  document.getElementById("select-none").addEventListener("click", () => {
    archiveTabs.forEach(t => (t.selected = false));
    document.querySelectorAll(".tab-checkbox").forEach(cb => (cb.checked = false));
    refreshUI();
  });

  // Resume if a run was in progress when popup was closed; otherwise restore the
  // "Export Locked List" button if the last completed run left locked items.
  const { downloadStatus: s } = await api.storage.local.get("downloadStatus");
  if (s && !s.done) {
    setRunning(true);
    setStatus(`${s.completed ?? 0} / ${s.total ?? "?"} items processed…`);
    pollTimer = setInterval(pollStatus, 600);
  } else if (s && s.done) {
    updateLockedExportBtn(s.items);
  }
});
