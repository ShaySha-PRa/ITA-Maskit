# Download ITA-Maskit.exe and install for the current user.
#   powershell -ExecutionPolicy Bypass -File scripts/install_windows.ps1
# Or without cloning:
#   irm https://raw.githubusercontent.com/ShaySha-PRa/ITA-Maskit/main/scripts/install_windows.ps1 | iex
#
# NOTE: keep this file ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = "ShaySha-PRa/ITA-Maskit"
$asset = "ITA-Maskit.exe"
$destDir = Join-Path $env:LOCALAPPDATA "ITA-Maskit"
$destExe = Join-Path $destDir $asset
$urls = @(
    "https://github.com/$repo/releases/download/windows/$asset",
    "https://github.com/$repo/releases/latest/download/$asset"
)

New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$downloaded = $false
foreach ($url in $urls) {
    Write-Host "Downloading $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $destExe -UseBasicParsing
        if ((Get-Item $destExe).Length -gt 1MB) {
            $downloaded = $true
            break
        }
    } catch {
        Write-Host "  skip: $($_.Exception.Message)"
    }
}

if (-not $downloaded) {
    throw "Download failed. Open https://github.com/$repo/releases and download $asset manually."
}

$Wsh = New-Object -ComObject WScript.Shell
$startDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Force -Path $startDir | Out-Null
$startLnk = Join-Path $startDir "ITA-Maskit.lnk"
$shortcut = $Wsh.CreateShortcut($startLnk)
$shortcut.TargetPath = $destExe
$shortcut.WorkingDirectory = $destDir
$shortcut.Description = "ITA-Maskit local data masking"
$shortcut.Save()

$desktop = [Environment]::GetFolderPath("Desktop")
if ($desktop) {
    $deskLnk = Join-Path $desktop "ITA-Maskit.lnk"
    $desk = $Wsh.CreateShortcut($deskLnk)
    $desk.TargetPath = $destExe
    $desk.WorkingDirectory = $destDir
    $desk.Description = "ITA-Maskit local data masking"
    $desk.Save()
}

Write-Host ""
Write-Host "Installed: $destExe"
Write-Host "Shortcuts: Start Menu and Desktop"
Write-Host "If Windows SmartScreen appears: More info -> Run anyway"
Write-Host "Launching..."
Start-Process -FilePath $destExe
