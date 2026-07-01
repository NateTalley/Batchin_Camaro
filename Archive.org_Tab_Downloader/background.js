// Service worker — metadata, downloads, Ollama agent.
// Chrome MV3: load deps via importScripts. Firefox: listed in manifest before this file.
if (typeof searchItems === "undefined") {
  importScripts("ia-service.js", "agent-tools.js", "ollama-client.js");
}

const api = globalThis.browser ?? globalThis.chrome;

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function probeAvailable(url) {
  try {
    let r = await fetch(url, { method: "HEAD", credentials: "include", redirect: "follow" });
    if (r.status === 405) {
      r = await fetch(url, { method: "GET", credentials: "include", redirect: "follow",
                             headers: { Range: "bytes=0-0" } });
    }
    return r.ok || r.status === 206;
  } catch (_) {
    return false;
  }
}

function safePath(str) {
  return str.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 200);
}

function buildFilename(itemId, fileName, oneFolder) {
  return oneFolder
    ? `Archive Downloads/${safePath(fileName)}`
    : `Archive Downloads/${safePath(itemId)}/${safePath(fileName)}`;
}

async function getStatus() {
  const { downloadStatus: s = {} } = await api.storage.local.get("downloadStatus");
  return s;
}
async function setStatus(patch) {
  const s = await getStatus();
  await api.storage.local.set({ downloadStatus: { ...s, ...patch } });
}
async function setItemStatus(itemId, patch) {
  const s = await getStatus();
  s.items = s.items || {};
  s.items[itemId] = { ...(s.items[itemId] || {}), ...patch };
  await api.storage.local.set({ downloadStatus: s });
}

async function isStopped() {
  const s = await getStatus();
  return !!s.stopRequested;
}

async function exportDataFile(content, mimeType, filename) {
  const encoded = encodeURIComponent(content);
  const url     = `data:${mimeType};charset=utf-8,${encoded}`;
  await api.downloads.download({
    url,
    filename: `Archive Downloads/${filename}`,
    conflictAction: "overwrite"
  });
}

async function getAgentStatus() {
  const { agentStatus: s = {} } = await api.storage.local.get("agentStatus");
  return s;
}

async function setAgentStatus(patch) {
  const s = await getAgentStatus();
  await api.storage.local.set({ agentStatus: { ...s, ...patch } });
}

// ── Message handler ───────────────────────────────────────────────────────────

api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "START_DOWNLOADS") {
    runDownloads(msg.items, msg.options).catch(console.error);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "DOWNLOAD_BY_IDS") {
    const items = (msg.itemIds || []).map(id => ({ id, title: id, tabId: null }));
    runDownloads(items, msg.options).catch(console.error);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "SEARCH_ARCHIVE") {
    searchItems(msg.query, { mediatype: msg.mediatype, rows: msg.rows })
      .then(r => sendResponse({ ok: true, results: r }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
  if (msg.action === "AGENT_CHAT") {
    runAgentChat(msg).catch(e => setAgentStatus({ running: false, error: e.message, done: true }));
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "LIST_OLLAMA_MODELS") {
    listOllamaModels(msg.baseUrl || "http://127.0.0.1:11434")
      .then(m => sendResponse({ ok: true, models: m }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
});

async function agentDownloadHandler(itemIds, fmtOpts) {
  const stored = await api.storage.local.get([
    "wantExtra", "wantZip", "wantOneFolder", "exportTxt", "exportCsv", "exportJson", "sizeLimitGb",
    "iaAccessKey", "iaSecretKey"
  ]);
  const authHeader = stored.iaAccessKey && stored.iaSecretKey
    ? `LOW ${stored.iaAccessKey}:${stored.iaSecretKey}` : null;
  const items = itemIds.map(id => ({ id, title: id, tabId: null }));
  await runDownloads(items, {
    wantText: fmtOpts.wantText !== false,
    wantPdf: fmtOpts.wantPdf !== false,
    wantExtra: stored.wantExtra ?? false,
    wantZip: stored.wantZip ?? false,
    wantOneFolder: stored.wantOneFolder ?? false,
    exportTxt: stored.exportTxt ?? false,
    exportCsv: stored.exportCsv ?? false,
    exportJson: stored.exportJson ?? false,
    sizeLimitGb: stored.sizeLimitGb ?? 0,
    authHeader
  });
}

async function runAgentChat(msg) {
  const baseUrl = msg.baseUrl || "http://127.0.0.1:11434";
  const model = msg.model || "llama3.1";
  const userMessage = (msg.message || "").trim();
  if (!userMessage) return;

  const prev = await getAgentStatus();
  const messages = prev.messages || [{ role: "system", content: SYSTEM_PROMPT }];
  messages.push({ role: "user", content: userMessage });

  await setAgentStatus({
    running: true, done: false, error: null,
    transcript: (prev.transcript || "") + `\nYou: ${userMessage}\n`,
    toolLog: [], lastReply: ""
  });

  try {
    const result = await runAgentTurn({
      baseUrl, model, messages,
      downloadHandler: agentDownloadHandler
    });
    let transcript = (prev.transcript || "") + `\nYou: ${userMessage}\n`;
    for (const line of result.toolLog) transcript += `  [tool] ${line}\n`;
    transcript += `Assistant: ${result.content}\n`;
    await setAgentStatus({
      running: false, done: true, error: null,
      messages: result.messages, transcript,
      toolLog: result.toolLog, lastReply: result.content
    });
  } catch (e) {
    await setAgentStatus({
      running: false, done: true, error: e.message,
      transcript: (prev.transcript || "") + `\nYou: ${userMessage}\nError: ${e.message}\n`
    });
  }
}

// ── Main download loop ────────────────────────────────────────────────────────

async function runDownloads(items, opts) {
  const {
    wantText, wantPdf, wantExtra, wantZip,
    wantOneFolder, exportTxt, exportCsv, exportJson,
    sizeLimitGb, authHeader
  } = opts;

  const limitBytes = sizeLimitGb > 0 ? sizeLimitGb * 1024 ** 3 : 0;
  const authHeaders = authHeader ? [{ name: "Authorization", value: authHeader }] : undefined;

  const initItems = {};
  for (const item of items) {
    initItems[item.id] = { status: "pending", title: item.title };
  }
  await api.storage.local.set({
    downloadStatus: { items: initItems, total: items.length, completed: 0, done: false }
  });

  let completed = 0;

  for (const item of items) {
    if (await isStopped()) {
      await setItemStatus(item.id, { status: "stopped" });
      break;
    }

    await setItemStatus(item.id, { status: "fetching" });

    try {
      if (wantZip && !wantText && !wantPdf && !wantExtra) {
        const url      = `https://archive.org/compress/${item.id}`;
        const filename = buildFilename(item.id, `${item.id}.zip`, wantOneFolder);
        const dlOpts   = { url, filename, conflictAction: "overwrite" };
        if (authHeaders) dlOpts.headers = authHeaders;
        await api.downloads.download(dlOpts);
        await setItemStatus(item.id, { status: "done", filesDownloaded: 1, filesCount: 1 });
      } else {
        const resp = await fetch(`https://archive.org/metadata/${item.id}`);
        if (!resp.ok) throw new Error(`Metadata HTTP ${resp.status}`);
        const data  = await resp.json();

        const restricted = isRestricted(data);

        const files = filterDownloadableFiles(data, {
          wantText, wantPdf, wantExtra
        });

        const zipQueued = wantZip ? 1 : 0;
        const total     = files.length + zipQueued;

        if (total === 0) {
          await setItemStatus(item.id, { status: restricted ? "restricted" : "no_files", filesCount: 0, restricted });
        } else {
          await setItemStatus(item.id, { status: "downloading", filesCount: total, filesDownloaded: 0, skippedSize: 0, unavailable: 0, restricted });

          let downloaded = 0, skippedSize = 0, unavailable = 0;

          const queue = async (url, name) => {
            if (!(await probeAvailable(url))) {
              unavailable++;
              await setItemStatus(item.id, { unavailable });
              return;
            }
            const filename = buildFilename(item.id, name, wantOneFolder);
            const dlOpts   = { url, filename, conflictAction: "overwrite" };
            if (authHeaders) dlOpts.headers = authHeaders;
            try {
              await api.downloads.download(dlOpts);
              downloaded++;
              await setItemStatus(item.id, { filesDownloaded: downloaded, skippedSize, unavailable });
            } catch (e) {
              console.warn(`Skipped ${name}:`, e.message);
              unavailable++;
              await setItemStatus(item.id, { unavailable });
            }
          };

          for (const f of files) {
            if (await isStopped()) break;

            const fileBytes = parseInt(f.size || "0", 10);
            if (limitBytes > 0 && fileBytes > limitBytes) {
              skippedSize++;
              await setItemStatus(item.id, { skippedSize });
              continue;
            }

            const url = `https://archive.org/download/${item.id}/${encodeURIComponent(f.name)}`;
            await queue(url, f.name);
            await delay(300);
          }

          if (wantZip && !(await isStopped())) {
            await queue(`https://archive.org/compress/${item.id}`, `${item.id}.zip`);
          }

          const finalState = (downloaded === 0 && unavailable > 0)
            ? (restricted ? "restricted" : "no_files")
            : "done";
          await setItemStatus(item.id, { status: finalState, skippedSize, unavailable, restricted });
        }
      }
    } catch (err) {
      await setItemStatus(item.id, { status: "error", error: err.message });
    }

    if (item.tabId) { try { await api.tabs.remove(item.tabId); } catch (_) {} }

    completed++;
    await setStatus({ completed });
    await delay(400);
  }

  const finalStatus = await getStatus();
  const unavailable = Object.entries(finalStatus.items || {})
    .filter(([, st]) => st.status === "no_files" || st.status === "error" || st.status === "restricted")
    .map(([id, st]) => ({ id, title: st.title || "", status: st.status, error: st.error || "" }));

  if (unavailable.length > 0) {
    if (exportTxt) {
      const lines = unavailable.map(u => `${u.id}\t${u.title}\t${u.status}\t${u.error}`);
      await exportDataFile("id\ttitle\tstatus\terror\n" + lines.join("\n"), "text/plain", "unavailable.txt");
    }
    if (exportCsv) {
      const q   = s => `"${s.replace(/"/g, '""')}"`;
      const rows = unavailable.map(u => [q(u.id), q(u.title), q(u.status), q(u.error)].join(","));
      await exportDataFile("id,title,status,error\n" + rows.join("\n"), "text/csv", "unavailable.csv");
    }
    if (exportJson) {
      await exportDataFile(JSON.stringify(unavailable, null, 2), "application/json", "unavailable.json");
    }
  }

  await setStatus({ done: true });
}
