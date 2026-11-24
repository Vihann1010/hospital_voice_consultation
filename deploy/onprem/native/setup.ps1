# Evanta HMS: portable install (no Docker, no services, nothing on C: except Windows temp use by the downloader).
# Everything goes under one folder. To remove it all: run stop.ps1, then delete the folder.
# Run from the unzipped bundle folder:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
param([string]$Root = "D:\EvantaHMS", [string]$LanIp = "10.8.0.100", [string]$HubKey = "", [switch]$Force)
$ErrorActionPreference = "Stop"; $ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Bundle = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m) }
function Rand($n) { -join ((48..57 + 65..90 + 97..122) | Get-Random -Count $n | ForEach-Object { [char]$_ }) }

# ---- pre-flight (refuses to continue if the PC is too tight) ----
$drive = (Split-Path -Qualifier $Root)
$freeGB = [math]::Round((Get-PSDrive ($drive.TrimEnd(':'))).Free / 1GB, 1)
if ($freeGB -lt 6) { throw "Only $freeGB GB free on $drive. Need 6 GB. Stopping." }
$freeMB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
Say "Free RAM now: $freeMB MB. Free space on ${drive}: $freeGB GB."
if ($freeMB -lt 900 -and -not $Force) { throw "Free RAM is only $freeMB MB. Installing may slow Onito. Stopping. (Use -Force only if told to.)" }
if (Test-Path "$Root\.installed") { throw "$Root is already installed. Use start.ps1." }

foreach ($d in "tools", "app", "data\pg", "data\media", "logs", "backups", "tmp") { New-Item -ItemType Directory -Force -Path "$Root\$d" | Out-Null }
$env:TEMP = "$Root\tmp"; $env:TMP = "$Root\tmp"

# ---- copy the app ----
Say "Copying the app"
Copy-Item -Recurse -Force "$Bundle\app\*" "$Root\app\"
Copy-Item -Force "$Bundle\*.ps1" "$Root\" -Exclude "setup.ps1"
Copy-Item -Force "$Bundle\setup.ps1" "$Root\setup.ps1"
Copy-Item -Force "$Bundle\updater.py" "$Root\updater.py"
Copy-Item -Force "$Bundle\VERSION" "$Root\VERSION"
Copy-Item -Force "$Bundle\https\Caddyfile" "$Root\Caddyfile"

function Get-Zip($url, $dest) {
  $zip = "$Root\tmp\" + [IO.Path]::GetFileName($url)
  if (-not (Test-Path $zip)) { Say "Downloading $url"; Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing }
  Say "Unpacking to $dest"; New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Expand-Archive -Path $zip -DestinationPath $dest -Force
  Remove-Item $zip -Force
}

# ---- local HTTPS (Caddy): a front door at 127.0.0.1:3443, HTTP stays internal-only on 8000/3000 ----
$caddy = "$Root\tools\caddy"
if (-not (Test-Path "$caddy\caddy.exe")) {
  New-Item -ItemType Directory -Force -Path $caddy | Out-Null
  Get-Zip "https://github.com/caddyserver/caddy/releases/download/v2.11.9/caddy_2.11.9_windows_amd64.zip" $caddy
}
# Caddy makes its OWN local certificate authority the first time it runs (nothing from us, nothing shared
# between hospitals) and signs a 127.0.0.1 certificate from it. `caddy trust` puts that CA into Windows'
# trust store so the padlock is real; it needs administrator rights, same as the update tasks below, so a
# non-administrator run is told to do this afterwards rather than silently skipping it.
$env:XDG_DATA_HOME = "$Root\data\caddy"; $env:XDG_CONFIG_HOME = "$Root\data\caddy"
Push-Location $Root
try {
  & "$caddy\caddy.exe" validate --config "$Root\Caddyfile" 2>&1 | Out-Null
  if ($LASTEXITCODE) { throw "Caddyfile did not validate" }
  & "$caddy\caddy.exe" trust 2>&1 | Out-Null
  if ($LASTEXITCODE) { Say "Could not install the local HTTPS certificate (needs an administrator PowerShell). Run: $caddy\caddy.exe trust" }
  else { Say "Local HTTPS certificate trusted" }
} finally { Pop-Location }

# ---- Python (embeddable) + pip + packages (OCR is NOT installed) ----
$py = "$Root\tools\python"
if (-not (Test-Path "$py\python.exe")) {
  Get-Zip "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip" $py
  $pth = Get-ChildItem "$py\python3*._pth" | Select-Object -First 1
  (Get-Content $pth.FullName) -replace '^#\s*import site', 'import site' | Set-Content $pth.FullName
  # The embedded Python ignores PYTHONPATH and the current folder, so the app folder must be listed here or `-m scripts...` and `app.main` are not found.
  Add-Content $pth.FullName "$Root\app\backend"
  Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$Root\tmp\get-pip.py" -UseBasicParsing
  & "$py\python.exe" "$Root\tmp\get-pip.py" --no-warn-script-location --no-cache-dir
  if ($LASTEXITCODE) { throw "pip install failed" }
}
Say "Installing Python packages (a few minutes)"
& "$py\python.exe" -m pip install --no-cache-dir --no-warn-script-location --only-binary=:all: -r "$Root\app\backend\requirements-pilot.txt"
if ($LASTEXITCODE) { throw "Python packages failed to install. Send the message above to Evanta. Nothing else was changed." }

# ---- Node ----
if (-not (Test-Path "$Root\tools\node\node.exe")) {
  Get-Zip "https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip" "$Root\tools"
  Rename-Item "$Root\tools\node-v20.18.1-win-x64" "$Root\tools\node"
}

# ---- Postgres (portable binaries) ----
$pg = "$Root\tools\pgsql"
if (-not (Test-Path "$pg\bin\postgres.exe")) { Get-Zip "https://get.enterprisedb.com/postgresql/postgresql-16.9-1-windows-x64-binaries.zip" "$Root\tools" }
$dbpass = Rand 28
if (-not (Test-Path "$Root\data\pg\PG_VERSION")) {
  Say "Creating the database"
  Set-Content -Path "$Root\tmp\pw.txt" -Value $dbpass -NoNewline
  & "$pg\bin\initdb.exe" -D "$Root\data\pg" -U postgres -A scram-sha-256 --pwfile="$Root\tmp\pw.txt" -E UTF8 --locale=C
  if ($LASTEXITCODE) { throw "initdb failed" }
  Remove-Item "$Root\tmp\pw.txt" -Force
  Add-Content "$Root\data\pg\postgresql.conf" @"

# Evanta: small footprint so the live hospital system is never starved
listen_addresses = '127.0.0.1'
port = 5444
max_connections = 25
shared_buffers = 48MB
work_mem = 2MB
maintenance_work_mem = 32MB
effective_cache_size = 256MB
max_wal_size = 256MB
min_wal_size = 32MB
logging_collector = on
log_directory = '$($Root.Replace('\','/'))/logs'
log_filename = 'postgres-%a.log'
"@
}

# ---- settings file (secrets generated here, never printed) ----
if (-not (Test-Path "$Root\app\backend\.env")) {
  $adminPw = Rand 14; $dr1 = Rand 14; $dr2 = Rand 14
  $env_text = @"
APP_ENV=production
DEBUG=false
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5444
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$dbpass
POSTGRES_DB=satya_hospital
JWT_SECRET_KEY=$(Rand 48)
ADMIN_PASSWORD=$adminPw
DR_AK_AGARWAL_PASSWORD=$dr1
DR_MANISHA_AGARWAL_PASSWORD=$dr2
CORS_ORIGINS=http://${LanIp}:3000,http://localhost:3000
MEDIA_ROOT=$Root\data\media
ENABLED_MODULES=reception,consultations
RATE_LIMIT_ENABLED=true
PILOT_API_URL=http://127.0.0.1:8000
PILOT_BRIDGE_KEY=$(Rand 40)
AI_GATEWAY_URL=https://hub.evantahealth.com
AI_GATEWAY_KEY=$HubKey
EVANTA_ROOT=$Root
ONITO_BASE_URL=http://${LanIp}:7080
ONITO_USERNAME=
ONITO_PASSWORD=
ONITO_WRITES_ENABLED=false
ONITO_EMR_WRITES_ENABLED=false
"@
  Set-Content -Path "$Root\app\backend\.env" -Value $env_text -Encoding ASCII
  Set-Content -Path "$Root\LOGINS.txt" -Value "Admin login: admin@satyahospital.in`r`nAdmin password: $adminPw`r`n(Keep this file private. Delete it after you save the password elsewhere.)" -Encoding ASCII
}

# ---- start the database, create the schema ----
$env:PATH = "$py;$py\Scripts;$pg\bin;$env:PATH"
Push-Location "$Root\app\backend"
try {
  & "$pg\bin\pg_ctl.exe" -D "$Root\data\pg" -l "$Root\logs\pg-start.log" -w start
  if ($LASTEXITCODE) { throw "database did not start, see $Root\logs\pg-start.log" }
  $pw = ((Get-Content ".env") | Where-Object { $_ -like "POSTGRES_PASSWORD=*" }) -replace "POSTGRES_PASSWORD=", ""
  $env:PGPASSWORD = $pw
  & "$pg\bin\psql.exe" -h 127.0.0.1 -p 5444 -U postgres -d postgres -c "CREATE DATABASE satya_hospital" 2>&1 | Out-Null
  Say "Creating tables"
  & "$py\python.exe" -m scripts.migrate_fresh_install
  if ($LASTEXITCODE) { throw "migration failed" }
} finally { Pop-Location }

New-Item -ItemType File -Force -Path "$Root\.installed" | Out-Null
try { & "$Root\install-update-tasks.ps1" } catch { Write-Host "Update tasks NOT registered ($($_.Exception.Message)). Run install-update-tasks.ps1 from an administrator PowerShell." }
Say "DONE. Nothing is running yet except the database. Next: edit $Root\app\backend\.env (hub key, Onito login), then run start.ps1"
