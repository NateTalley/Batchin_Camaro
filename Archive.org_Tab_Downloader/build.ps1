# Assembles ready-to-load extension folders for both browsers under dist/.
#   dist/chrome   -> uses manifest.json          (service worker background)
#   dist/firefox  -> uses manifest.firefox.json  (event-page background)
#
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$shared = @(
  "background.js", "popup.html", "popup.css", "popup.js",
  "ia-service.js", "agent-tools.js", "ollama-client.js", "icons"
)

function Build-Target($name, $manifest) {
    $out = Join-Path $root "dist/$name"
    if (Test-Path $out) { Remove-Item $out -Recurse -Force }
    New-Item -ItemType Directory -Path $out -Force | Out-Null

    foreach ($item in $shared) {
        Copy-Item (Join-Path $root $item) -Destination $out -Recurse -Force
    }
    Copy-Item (Join-Path $root $manifest) -Destination (Join-Path $out "manifest.json") -Force
    Write-Host "Built dist/$name"
}

Build-Target "chrome"  "manifest.json"
Build-Target "firefox" "manifest.firefox.json"
Write-Host "Done."
