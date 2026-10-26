param(
    [string]$IpAddress = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not $IpAddress) {
    $candidate = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown" -and
            $_.InterfaceAlias -notmatch "Bluetooth|Loopback|vEthernet"
        } |
        Sort-Object @{Expression = { if ($_.InterfaceAlias -match "Wi-Fi|Wireless") { 0 } else { 1 } }} |
        Select-Object -First 1

    if ($candidate) {
        $IpAddress = $candidate.IPAddress
    }
}

if (-not $IpAddress) {
    Write-Host "Could not automatically find the LAN IPv4 address." -ForegroundColor Yellow
    Write-Host "Run: .\tools\run_tablet_https.ps1 -IpAddress 192.168.x.x"
    exit 1
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python ".\tools\generate_tablet_cert.py" --host $IpAddress --output ".\certs"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:HOST = "0.0.0.0"
$env:SSL_CERT_PATH = (Resolve-Path ".\certs\hri_server.pem").Path
$env:SSL_KEY_PATH = (Resolve-Path ".\certs\hri_server_key.pem").Path

Write-Host ""
Write-Host "Tablet URL: https://$IpAddress`:5000" -ForegroundColor Cyan
Write-Host "If this is the first iPad setup, install/trust certs\hri_local_ca.crt first." -ForegroundColor Yellow
Write-Host ""

& $python ".\app.py"
