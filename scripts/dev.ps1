# Development mode: backend on :8000 with --reload, Vite dev server on :5173
# (proxying /api to :8000, see frontend/vite.config.ts). Ctrl-C stops both.
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

. ".\.venv\Scripts\Activate.ps1"

$backend = Start-Process -FilePath "uvicorn" -ArgumentList "app.main:app", "--reload", "--port", "8000" -WorkingDirectory "backend" -PassThru -NoNewWindow

try {
    Set-Location frontend
    npm run dev
}
finally {
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
}
