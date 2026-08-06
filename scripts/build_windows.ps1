# ITA-Maskit Windows 打包脚本（PyInstaller）
# 在 Windows 上执行：powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# 产出：dist/ITA-Maskit.exe

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== 安装打包依赖 ==="
pip install pyinstaller PyQt5

Write-Host "=== 打包 ==="
pyinstaller `
  --name "ITA-Maskit" `
  --windowed `
  --onefile `
  --add-data "maskit;maskit" `
  --hidden-import "polars" `
  --hidden-import "typer" `
  --hidden-import "yaml" `
  --hidden-import "openpyxl" `
  --hidden-import "xlsxwriter" `
  --hidden-import "pypdf" `
  --hidden-import "docx" `
  --hidden-import "extract_msg" `
  maskit/gui_app.py

Write-Host "=== 完成 ==="
Write-Host "可执行文件: dist/ITA-Maskit.exe"
Write-Host "（图片裁剪需额外安装 tesseract OCR；未内置）"
