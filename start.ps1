# Start ProvenAI: the checker (backend) and the web app, each in its own window.
#
#   powershell -ExecutionPolicy Bypass -File start.ps1
#
# Optional settings (set them before running):
#   $env:PROVENAI_PYTHON     Python of the virtual environment, if it is not .venv or venv here
#   $env:PROVENAI_INDEX_DIR  Folder of the regulation index, if it is not .runtime\chroma

$root = $PSScriptRoot

# 1. Python with the backend requirements installed.
$python = $env:PROVENAI_PYTHON
if (-not $python) {
    foreach ($candidate in @("$root\.venv\Scripts\python.exe", "$root\venv\Scripts\python.exe", "$HOME\.venvs\provenai\Scripts\python.exe")) {
        if (Test-Path $candidate) { $python = $candidate; break }
    }
}
if (-not $python) { $python = "python" }
& $python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python at '$python' does not have the backend requirements. Run: pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# 2. The regulation index.
if (-not $env:PROVENAI_INDEX_DIR -and (Test-Path "$HOME\.provenai\index-new")) { $env:PROVENAI_INDEX_DIR = "$HOME\.provenai\index-new" }
$index = if ($env:PROVENAI_INDEX_DIR) { $env:PROVENAI_INDEX_DIR } else { "$root\.runtime\chroma" }
if (-not (Test-Path $index)) {
    Write-Host "No regulation index at $index. Build it first (see README), or set PROVENAI_INDEX_DIR." -ForegroundColor Yellow
}

# 3. Ollama with Mistral, which reads the documents.
try { Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null }
catch {
    Write-Host "Starting Ollama ..."
    try { Start-Process ollama -ArgumentList "serve" -WindowStyle Minimized } catch { Write-Host "Ollama is not installed. Install it from https://ollama.com and run: ollama pull ministral-3:8b" -ForegroundColor Red }
}

# 4. The checker on port 8000.
$backend = "`$env:PROVENAI_INDEX_DIR='$index'; Set-Location '$root'; & '$python' -m uvicorn backend.api:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backend

# 5. The web app on port 8080.
$web = Join-Path $root "web\app"
if (-not (Test-Path "$web\node_modules")) {
    Write-Host "Installing the web app (first run only) ..."
    Push-Location $web; npm install; Pop-Location
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$web'; npm run dev"

# 6. Open the app when the checker answers.
Write-Host "Waiting for the checker to start ..."
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "http://localhost:8000/lovable/health" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}
Start-Process "http://localhost:8080"
Write-Host "ProvenAI is running: http://localhost:8080  (close the two windows to stop it)" -ForegroundColor Green
