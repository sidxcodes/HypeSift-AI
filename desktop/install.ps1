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
$icon = Join-Path $PSScriptRoot 'hypesift.ico'
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
Write-Host "Done. Open 'HypeSift AI' from your Desktop or Start menu." -ForegroundColor Green
