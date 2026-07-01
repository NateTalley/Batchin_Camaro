#!/usr/bin/env bash
# Assembles ready-to-load extension folders for both browsers under dist/.
#   dist/chrome   -> uses manifest.json          (service worker background)
#   dist/firefox  -> uses manifest.firefox.json  (event-page background)
#
# Usage:  ./build.sh
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"

shared=(background.js popup.html popup.css popup.js ia-service.js agent-tools.js ollama-client.js icons)

build_target() {
  local name="$1" manifest="$2"
  local out="$root/dist/$name"
  rm -rf "$out"
  mkdir -p "$out"
  for item in "${shared[@]}"; do
    cp -R "$root/$item" "$out/"
  done
  cp "$root/$manifest" "$out/manifest.json"
  echo "Built dist/$name"
}

build_target chrome  manifest.json
build_target firefox manifest.firefox.json
echo "Done."
