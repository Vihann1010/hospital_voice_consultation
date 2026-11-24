# Stop everything of ours. Onito is never touched. Run: powershell -ExecutionPolicy Bypass -File D:\EvantaHMS\stop.ps1
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($n in "bridge", "guard", "caddy", "web", "api") {
  $f = "$Root\logs\$n.pid"
  if (Test-Path $f) {
    $id = Get-Content $f
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { & taskkill /PID $id /T /F | Out-Null }
    Remove-Item $f -Force
  }
}
& "$Root\tools\pgsql\bin\pg_ctl.exe" -D "$Root\data\pg" -m fast stop 2>&1 | Out-Null
Write-Host "Evanta HMS stopped. Onito was not touched."
