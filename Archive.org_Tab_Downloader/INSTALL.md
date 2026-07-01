# Install

Installation instructions for **Chrome** and **Firefox** now live in
[README.md](README.md).

## Ollama (for AI Agent tab)

The **AI Agent** tab talks to Ollama on your machine (`http://127.0.0.1:11434` by default).

1. Install [Ollama](https://ollama.com/).
2. Start the server: `ollama serve` (often automatic on install).
3. Pull a model: `ollama pull llama3.1` (or another tool-capable model).
4. In the extension **AI Agent** tab, click **Refresh** to verify connectivity.

Quick version:

1. Build the per-browser folders:
   - macOS / Linux / Git Bash: `./build.sh`
   - Windows PowerShell: `powershell -ExecutionPolicy Bypass -File build.ps1`
2. **Chrome / Edge / Brave:** `chrome://extensions` → enable *Developer mode* →
   **Load unpacked** → select `dist/chrome` (or the repo root).
3. **Firefox:** `about:debugging` → *This Firefox* → **Load Temporary Add-on…**
   → select `dist/firefox/manifest.json`.

See [README.md](README.md) for usage, IA S3 keys, and a permanent (signed)
Firefox install.
