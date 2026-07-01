# Archive Batch Downloader

A browser extension focused on **Internet Archive** downloading: OCR text and/or
searchable PDFs from open `archive.org/details/…` tabs (with optional tab close),
plus **search** and **AI-assisted downloads** via a local Ollama agent.
Works in **Chrome** (and Chromium browsers: Edge, Brave, Opera) and **Firefox**.

## Tabs

| Tab | Purpose |
| --- | --- |
| **Download** | Scan open IA tabs, pick formats, batch download |
| **AI Agent** | Chat with local Ollama to search archive.org and queue downloads |
| **Batch Tools** | Bridge to the desktop app for CSV → JSONL batch inference |

- Pick **OCR Text**, **Searchable PDF**, or both — plus optional images/docs,
  full ZIP archives, and per-file size limits.
- Downloads run in the background even if the popup is closed; progress is shown
  per tab.
- Optional Internet Archive S3 keys for authenticated/faster downloads.

Files are saved to: `Downloads/Archive Downloads/{item-id}/{filename}`

---

## Ollama AI Agent (local)

1. Install [Ollama](https://ollama.com/) and run `ollama serve`.
2. Pull a tool-capable model, e.g. `ollama pull llama3.1`.
3. Open the extension → **AI Agent** tab → **Refresh** to list models.
4. Example prompts:
   - *Search archive.org for public domain books about astronomy*
   - *Get metadata for identifier `alicesadventures19033gut`*
   - *Download OCR text for these items: …*

The agent uses tools (`search_archive`, `get_item_metadata`, `start_download`) against
archive.org APIs. Downloads use your current format settings from the ⚙️ panel.

---

## What's in this folder

| File | Used by |
| --- | --- |
| `manifest.json` | Chrome (Manifest V3, service-worker background) |
| `manifest.firefox.json` | Firefox (Manifest V3, event-page background) |
| `background.js`, `popup.html`, `popup.css`, `popup.js`, `icons/` | shared by both |
| `ia-service.js`, `agent-tools.js`, `ollama-client.js` | IA API + Ollama agent |
| `build.sh` / `build.ps1` | assemble per-browser folders under `dist/` |

The two browsers need a differently-shaped `background` entry in their manifest,
so each one loads from its own folder. The build script copies the shared files
plus the correct manifest into `dist/chrome/` and `dist/firefox/`.

```bash
# macOS / Linux / Git Bash
./build.sh
```

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This produces:

```
dist/chrome/    <- load this in Chrome
dist/firefox/   <- load this in Firefox
```

> You can skip the build for Chrome and load the repo root directly (its
> `manifest.json` is already the Chrome one). Firefox requires a folder whose
> manifest is named `manifest.json`, so run the build first for Firefox.

---

## Install in Chrome / Edge / Brave (unpacked)

1. Run the build (or use the repo root for Chrome).
2. Open `chrome://extensions` (Edge: `edge://extensions`, Brave: `brave://extensions`).
3. Enable **Developer mode** (top-right toggle).
4. Click **Load unpacked**.
5. Select the **`dist/chrome`** folder (or the repo root).
6. The 📦 extension icon appears in your toolbar.

The extension stays installed across restarts.

---

## Install in Firefox

Firefox loads unpacked extensions as **temporary add-ons** (removed when Firefox
closes). For a permanent install you'd need a signed `.xpi` — see below.

1. Run the build: `./build.sh` (or `build.ps1`) to create `dist/firefox`.
2. Open `about:debugging` in Firefox.
3. Click **This Firefox** in the left sidebar.
4. Click **Load Temporary Add-on…**.
5. Select the **`dist/firefox/manifest.json`** file.
6. The 📦 extension icon appears in your toolbar.

### Notes for Firefox

- **Temporary add-ons are removed when Firefox restarts.** Re-load it from
  `about:debugging` each session, or package a signed `.xpi` (below).
- If downloads from archive.org are blocked, open `about:addons` → this
  extension → **Permissions**, and ensure access to `archive.org` is allowed.
- Firefox Developer Edition / Nightly let you disable signature enforcement
  (`xpi.signatures.required = false` in `about:config`) if you prefer to install
  a packaged `.xpi` without signing.

### Optional: packaged / signed install

To install permanently in regular Firefox, sign the add-on through Mozilla:

```bash
# one-time: npm install --global web-ext
cd dist/firefox
web-ext sign --api-key=<JWT issuer> --api-secret=<JWT secret>
```

Get API credentials at <https://addons.mozilla.org/developers/addon/api/key/>.
`web-ext sign` returns a signed `.xpi` you can install via `about:addons` →
gear icon → **Install Add-on From File…**.

---

## Usage

1. Open several Internet Archive item pages (`archive.org/details/…`).
2. Click the extension icon.
3. Choose **OCR Text**, **Searchable PDF**, or both. Open the ⚙️ settings panel
   for extra formats, full-ZIP downloads, folder layout, size limits, and IA S3
   keys.
4. Uncheck any tabs you want to skip.
5. Click **Download & Close Tabs**.

Each tab is closed once its files are queued; downloading continues in the
background. Items with no matching files for the selected format show **— none**
and their tab is still closed.

### Exporting lists

- **Export URLs** (tab list header) — saves a CSV of every open archive.org tab
  (`id, title, url`) to `Downloads/Archive Downloads/archive-tab-urls.csv`.
  Handy for saving your queue before downloading.
- **Export Locked List (CSV)** — appears under the action button after a run
  finishes if any items were locked/unavailable. Saves the borrow-only,
  no-files, and errored items (`id, title, status, url`) to
  `Downloads/Archive Downloads/locked-items.csv` so you can track them down
  another way later.

### Authenticated downloads (optional)

Open the ⚙️ panel and enter your Internet Archive **S3 access/secret keys**
(from <https://archive.org/account/s3.php>). Keys are stored locally via
`storage.local` and sent as `Authorization: LOW key:secret` on download
requests.

---

## What gets downloaded

- **OCR Text** saves the plain-text OCR file `{item}_djvu.txt` (or the item's
  `.txt`) — *not* the `_hocr.html`, `_chocr.html.gz`, `_abbyy.gz`, `_djvu.xml`,
  or `_hocr_pageindex.json.gz` derivatives, which are not readable text.
- **Searchable PDF** saves the text PDF `{item}.pdf` — not the encrypted/LCP or
  JPEG-compressed PDF variants.

Before saving, each file is probed (with your archive.org cookies) to confirm
it's actually downloadable, so a locked file is never written to disk as a
broken `.html`/`.txt` error page.

### Borrow-only / access-restricted items 🔒

Items in the `inlibrary` / `printdisabled` collections (lending library books)
are **access-restricted**: every file returns `401/403` unless you are logged
in to archive.org *and* currently have that book borrowed. The extension marks
these **🔒 locked** and skips them instead of saving failed downloads. To get
their text/PDF you must borrow the book in your browser first (the extension
then uses your session automatically).

## Notes

- A 300 ms delay is inserted between files and 400 ms between items to avoid
  hammering the servers (mirrors the rate-limiting in `batchincamaro.py`).
- Re-running on the same item overwrites existing files
  (`conflictAction: "overwrite"`).
- If you are logged in to archive.org in the browser, your session cookies are
  used automatically for faster / authenticated downloads.
