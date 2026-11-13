# HypeSift AI - desktop launcher (Windows).
# Started by HypeSift.vbs (no console window). Opens an app window right away with a
# startup screen, starts Ollama (if installed), the API and the web app in the
# background, and stops the API and web app again when the last HypeSift window closes.
# Logs: %LOCALAPPDATA%\HypeSift\logs

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$ApiPort  = 8765
$WebPort  = 3765
$AppUrl   = "http://127.0.0.1:$WebPort/app"
$DataDir  = Join-Path $env:LOCALAPPDATA 'HypeSift'
$Logs     = Join-Path $DataDir 'logs'
$WinProfile = Join-Path $DataDir 'app-window'   # separate browser profile = separate app window + saved login
New-Item -ItemType Directory -Force $Logs, $WinProfile | Out-Null
$LauncherLog = Join-Path $Logs 'launcher.log'

function Log($msg) { Add-Content -Path $LauncherLog -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding utf8 }

function Show-Error($msg) {
    Log "ERROR: $msg"
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("$msg`n`nLogs: $Logs", 'HypeSift AI', 'OK', 'Error') | Out-Null
}

function Test-Port($port) {
    $c = New-Object Net.Sockets.TcpClient
    try { $c.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $c.Close() }
}

function Wait-Url($url, $seconds, $proc) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if ($proc -and $proc.HasExited) { return $false }
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -lt 500) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Find-Edge {
    foreach ($p in @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
                     "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Open-Window($target) {
    $edge = Find-Edge
    if (-not $edge) { Start-Process $AppUrl; return }   # fall back to the default browser
    $edgeArgs = @("--app=$target", "--user-data-dir=`"$WinProfile`"", '--no-first-run', '--no-default-browser-check',
              '--window-size=1440,900', '--disable-features=msEdgeSidebarV2,msHubApps')
    Start-Process -FilePath $edge -ArgumentList $edgeArgs | Out-Null
}

function Get-WindowProcs {
    Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($WinProfile) }
}

function Stop-Tree($proc) {
    if ($proc -and -not $proc.HasExited) { & taskkill.exe /PID $proc.Id /T /F 2>$null | Out-Null }
}

Log "---- launch ----"

# Already running? Just open another window.
if ((Test-Port $WebPort) -and (Test-Port $ApiPort)) {
    Log "servers already running; opening a window"
    Open-Window $AppUrl
    exit 0
}

$py = Join-Path $Backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Show-Error "Python environment not found at $py.`nRun desktop\install.ps1 first."; exit 1 }
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) { Show-Error "Node.js was not found. Install Node.js 20+ and try again."; exit 1 }

# 1. Window first, so something appears instantly.
$splash = 'file:///' + ((Join-Path $PSScriptRoot 'splash.html') -replace '\\', '/' -replace ' ', '%20')
Open-Window $splash

# 2. Local AI editor (optional, free). Left running afterwards; it unloads models on its own when idle.
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if ((Test-Path $ollama) -and -not (Test-Port 11434)) {
    Log "starting ollama"
    Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
}

# 3. API + background worker.
$env:HYPESIFT_EMBEDDED_WORKER = 'true'
$env:PYTHONUNBUFFERED = '1'
$api = Start-Process -FilePath $py -WorkingDirectory $Backend -WindowStyle Hidden -PassThru `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort" `
    -RedirectStandardOutput (Join-Path $Logs 'api.out.log') -RedirectStandardError (Join-Path $Logs 'api.log')
Log "api pid $($api.Id)"

# 4. Web app: production build, rebuilt automatically when the code changes.
$env:NEXT_DIST_DIR = '.next-app'
$env:HYPESIFT_API_URL = "http://127.0.0.1:$ApiPort"
$env:NEXT_TELEMETRY_DISABLED = '1'
$nextBin = Join-Path $Frontend 'node_modules\next\dist\bin\next'
$stamp = Join-Path $Frontend '.next-app\hypesift-build.txt'
$srcHash = (Get-ChildItem -Path (Join-Path $Frontend 'src'), (Join-Path $Frontend 'public') -Recurse -File |
            Sort-Object FullName | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }) -join "`n"
$srcHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($srcHash))) -replace '-', ''
$needBuild = -not (Test-Path $stamp) -or ((Get-Content $stamp -Raw).Trim() -ne $srcHash)
if ($needBuild) {
    Log "building web app"
    $build = Start-Process -FilePath $node -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru -Wait `
        -ArgumentList "`"$nextBin`"", 'build' `
        -RedirectStandardOutput (Join-Path $Logs 'build.out.log') -RedirectStandardError (Join-Path $Logs 'build.log')
    if ($build.ExitCode -ne 0) { Stop-Tree $api; Show-Error "Building the web app failed."; exit 1 }
    Set-Content -Path $stamp -Value $srcHash -Encoding ascii
}

if (-not (Wait-Url "http://127.0.0.1:$ApiPort/api/health" 120 $api)) {
    Stop-Tree $api; Show-Error "The HypeSift API did not start."; exit 1
}
$web = Start-Process -FilePath $node -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru `
    -ArgumentList "`"$nextBin`"", 'start', '-H', '127.0.0.1', '-p', "$WebPort" `
    -RedirectStandardOutput (Join-Path $Logs 'web.out.log') -RedirectStandardError (Join-Path $Logs 'web.log')
Log "web pid $($web.Id)"
if (-not (Wait-Url "http://127.0.0.1:$WebPort/manifest.webmanifest" 60 $web)) {
    Stop-Tree $web; Stop-Tree $api; Show-Error "The HypeSift web app did not start."; exit 1
}
Log "ready"

# 5. Keep running while any HypeSift window is open, then shut the servers down.
Start-Sleep -Seconds 5
while (@(Get-WindowProcs).Count -gt 0) {
    if ($api.HasExited) { Log "api exited unexpectedly"; break }
    Start-Sleep -Seconds 3
}
Log "windows closed; stopping servers"
Stop-Tree $web
Stop-Tree $api
Log "stopped"

# 6. Keep the YouTube downloader current. Sites change often and yt-dlp ships fixes within days,
#    so refresh it (free, from PyPI) every 3 days - after closing, so it never slows a launch.
$ytStamp = Join-Path $DataDir 'yt-dlp-updated.txt'
$ytAge = if (Test-Path $ytStamp) { (Get-Date) - (Get-Item $ytStamp).LastWriteTime } else { [TimeSpan]::MaxValue }
if ($ytAge.TotalDays -ge 3) {
    Log "updating yt-dlp"
    $upd = Start-Process -FilePath $py -WindowStyle Hidden -PassThru -Wait `
        -ArgumentList '-m', 'pip', 'install', '--upgrade', '--quiet', '--disable-pip-version-check', 'yt-dlp' `
        -RedirectStandardOutput (Join-Path $Logs 'yt-dlp-update.out.log') -RedirectStandardError (Join-Path $Logs 'yt-dlp-update.log')
    if ($upd.ExitCode -eq 0) { Set-Content -Path $ytStamp -Value (Get-Date -Format o) -Encoding ascii }
    Log "yt-dlp update exit $($upd.ExitCode)"
}
