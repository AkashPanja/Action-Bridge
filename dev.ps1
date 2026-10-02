# Action Bridge dev launcher — starts backend (auto-reload) + frontend (hot reload)
# Usage: ./dev.ps1        (start both)
#        ./dev.ps1 -Kill  (stop both)

param([switch]$Kill)

if ($Kill) {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*vite*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Dev servers stopped."
    exit 0
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")
$root = $PSScriptRoot

# Refuse to start twice
$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*vite*" }
if ($running) { Write-Host "Dev servers already running. Use ./dev.ps1 -Kill first."; exit 1 }

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\backend'; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -WindowStyle Minimized

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev" -WindowStyle Minimized

Write-Host "Starting dev servers..."
Write-Host "  API      -> http://localhost:8000  (auto-reload on backend changes)"
Write-Host "  Frontend -> http://localhost:5173  (hot reload on frontend changes)"
Write-Host "  Stop with: ./dev.ps1 -Kill"
