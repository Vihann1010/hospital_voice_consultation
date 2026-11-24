# Start Evanta HMS. Low priority so Onito always wins. Run:  powershell -ExecutionPolicy Bypass -File D:\EvantaHMS\start.ps1
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "$Root\tools\python"; $pg = "$Root\tools\pgsql"; $node = "$Root\tools\node"; $caddy = "$Root\tools\caddy"
$env:PATH = "$py;$py\Scripts;$pg\bin;$node;$env:PATH"; $env:TEMP = "$Root\tmp"; $env:TMP = "$Root\tmp"
$free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
if ($free -lt 700) { Write-Host "Free RAM only $free MB. Not starting."; exit 1 }

& "$pg\bin\pg_ctl.exe" -D "$Root\data\pg" status *> $null
if ($LASTEXITCODE) { & "$pg\bin\pg_ctl.exe" -D "$Root\data\pg" -l "$Root\logs\pg-start.log" -w start | Out-Null }

function Launch($name, $exe, $argList, $wd, $envs) {
  foreach ($k in $envs.Keys) { Set-Item "env:$k" $envs[$k] }
  $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $wd -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$Root\logs\$name.out.log" -RedirectStandardError "$Root\logs\$name.err.log"
  try { $p.PriorityClass = "BelowNormal" } catch {}
  Set-Content "$Root\logs\$name.pid" $p.Id
}
if (-not (Test-Path "$Root\logs\api.pid") -or -not (Get-Process -Id (Get-Content "$Root\logs\api.pid") -ErrorAction SilentlyContinue)) {
  Launch "api" "$py\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1" "$Root\app\backend" @{ PYTHONPATH = "$Root\app\backend" }
}
if (-not (Test-Path "$Root\logs\web.pid") -or -not (Get-Process -Id (Get-Content "$Root\logs\web.pid") -ErrorAction SilentlyContinue)) {
  Launch "web" "$node\node.exe" "--max-old-space-size=192 server.js" "$Root\app\frontend" @{ PORT = "3000"; HOSTNAME = "0.0.0.0"; NODE_ENV = "production" }
}
if (-not (Test-Path "$Root\logs\guard.pid") -or -not (Get-Process -Id (Get-Content "$Root\logs\guard.pid") -ErrorAction SilentlyContinue)) {
  $g = Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Root\guard.ps1`"" -WindowStyle Hidden -PassThru
  Set-Content "$Root\logs\guard.pid" $g.Id
}
if (Test-Path "$caddy\caddy.exe") {
  if (-not (Test-Path "$Root\logs\caddy.pid") -or -not (Get-Process -Id (Get-Content "$Root\logs\caddy.pid") -ErrorAction SilentlyContinue)) {
    Launch "caddy" "$caddy\caddy.exe" "run --config `"$Root\Caddyfile`" --adapter caddyfile" "$Root" @{ XDG_DATA_HOME = "$Root\data\caddy"; XDG_CONFIG_HOME = "$Root\data\caddy" }
  }
} else { Write-Host "No local HTTPS yet (tools\caddy missing) — the HMS still works at http://<this PC>:3000, just not the app window, which needs https://127.0.0.1:3443." }
Start-Sleep 8
& "$Root\status.ps1"
