# One-time setup for the HypeSift AI desktop app (Windows).
#   powershell -ExecutionPolicy Bypass -File desktop\install.ps1
# Installs dependencies if missing and creates "HypeSift AI" shortcuts on the Desktop and in the Start menu.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'

if (-not (Test-Path (Join-Path $Backend '.venv\Scripts\python.exe'))) {
    Write-Host "Creating Python environment..."
    python -m venv (Join-Path $Backend '.venv')
    & (Join-Path $Backend '.venv\Scripts\python.exe') -m pip install -r (Join-Path $Backend 'requirements.txt')
}
# YouTube / TikTok / Vimeo link import. Re-running this script also updates it to the latest release.
Write-Host "Updating the video-link downloader (yt-dlp)..."
& (Join-Path $Backend '.venv\Scripts\python.exe') -m pip install --upgrade --quiet --disable-pip-version-check yt-dlp
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Write-Host "Installing web app packages..."
    Push-Location $Frontend; npm install; Pop-Location
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and
    -not (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    Write-Host "FFmpeg not found. Install it with: winget install Gyan.FFmpeg" -ForegroundColor Yellow
}

$shell = New-Object -ComObject WScript.Shell
$vbs = Join-Path $PSScriptRoot 'HypeSift.vbs'
# Windows caches shortcut icons by file path, so a changed hypesift.ico can keep showing the old
# picture. Give every icon version its own file name: a new icon is then always a new path.
$iconSrc = Join-Path $PSScriptRoot 'hypesift.ico'
$iconDir = Join-Path $env:LOCALAPPDATA 'HypeSift\icons'
New-Item -ItemType Directory -Force $iconDir | Out-Null
$icon = Join-Path $iconDir ('hypesift-{0}.ico' -f (Get-FileHash $iconSrc -Algorithm SHA256).Hash.Substring(0, 10).ToLower())
if (-not (Test-Path $icon)) { Copy-Item $iconSrc $icon }
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $lnk = $shell.CreateShortcut((Join-Path $folder 'HypeSift AI.lnk'))
    $lnk.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    $lnk.Arguments = "`"$vbs`""
    $lnk.WorkingDirectory = $PSScriptRoot
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = 'HypeSift AI - turn long videos into ready-to-post shorts'
    $lnk.Save()
    Write-Host "Shortcut created: $($lnk.FullName)"
}
# Old icon versions are no longer used by any shortcut.
Get-ChildItem $iconDir -Filter 'hypesift-*.ico' | Where-Object { $_.FullName -ne $icon } | Remove-Item -ErrorAction SilentlyContinue
# Ask Explorer to redraw icons now instead of after the next sign-in.
& (Join-Path $env:WINDIR 'System32\ie4uinit.exe') -show
Add-Type -Namespace HypeSift -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'
[HypeSift.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)   # SHCNE_ASSOCCHANGED
Write-Host "Done. Open 'HypeSift AI' from your Desktop or Start menu." -ForegroundColor Green
