# What is running, how much memory we use, how much is free for Onito.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
"Free RAM: $free MB"
foreach ($n in "api", "web", "guard", "bridge", "caddy") {
  $f = "$Root\logs\$n.pid"; $p = $null
  if (Test-Path $f) { $p = Get-Process -Id (Get-Content $f) -ErrorAction SilentlyContinue }
  "{0,-7} {1}" -f $n, $(if ($p) { "running, " + [math]::Round($p.WorkingSet64/1MB) + " MB" } else { "stopped" })
}
$pgp = Get-Process postgres -ErrorAction SilentlyContinue
"db      " + $(if ($pgp) { "running, " + [math]::Round(($pgp | Measure-Object WorkingSet64 -Sum).Sum/1MB) + " MB (all db processes)" } else { "stopped" })
try { "api health: " + (Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/live -TimeoutSec 5 | ConvertTo-Json -Compress) } catch { "api health: not answering yet" }
try { "web: HTTP " + (Invoke-WebRequest http://127.0.0.1:3000 -UseBasicParsing -TimeoutSec 8).StatusCode } catch { "web: not answering yet" }
try { "local https (app window): HTTP " + (Invoke-WebRequest https://127.0.0.1:3443 -UseBasicParsing -TimeoutSec 8).StatusCode } catch { "local https (app window): not answering yet — run `"tools\caddy\caddy.exe trust`" as administrator if this PC never saw the certificate" }
