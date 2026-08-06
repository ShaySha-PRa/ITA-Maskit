# ITA-Maskit Windows 打包脚本（PyInstaller）
# 在 Windows 上执行（项目根目录下）：
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# 产出：dist/ITA-Maskit.exe（单文件，双击即用，无需装 Python）
#
# 前提：已安装 Python 3.10+（含 pip）。脚本会自动安装全部依赖。

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# 选择 Python：优先 py 启动器，回退 python
if (Get-Command py -ErrorAction SilentlyContinue) {
    $py = @("py", "-3")
} else {
    $py = @("python")
}
Write-Host "使用 Python: $($py -join ' ')"

Write-Host "=== 升级 pip ==="
& $py -m pip install --upgrade pip

Write-Host "=== 安装项目全部依赖（CLI + GUI + 图片 + LLM） ==="
& $py -m pip install -e ".[gui,image,llm]"
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

Write-Host "=== 安装 PyInstaller ==="
& $py -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 安装失败" }

Write-Host "=== 打包（ITA-Maskit.spec） ==="
& $py -m PyInstaller ITA-Maskit.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "打包失败" }

Write-Host ""
Write-Host "=== 完成 ==="
Write-Host "可执行文件: $PWD\dist\ITA-Maskit.exe（双击即用）"
Write-Host "注意："
Write-Host "  1. 图片脱敏（beta）需额外安装 tesseract OCR，未内置在 exe"
Write-Host "  2. AI 规则生成需设置环境变量 MASKIT_LLM_API_KEY"
Write-Host "  3. 建议用 GitHub Actions 自动构建产物（见 README）"
