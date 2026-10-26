param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if (-not (Test-Path ".\certs\hri_local_ca.crt")) {
    Write-Host "CA certificate does not exist yet." -ForegroundColor Yellow
    Write-Host "Run .\tools\run_tablet_https.ps1 once, stop it with Ctrl+C, then run this script."
    exit 1
}

Write-Host "Serving the HRI local CA on port $Port." -ForegroundColor Cyan
Write-Host "On the iPad, open http://<LAPTOP-IP>:$Port/hri_robot_ca.mobileconfig"
Write-Host "Press Ctrl+C after the certificate has downloaded."

& $python -m http.server $Port --bind 0.0.0.0 --directory ".\certs"
