# -*- mode: python ; coding: utf-8 -*-
"""ITA-Maskit PyInstaller spec（--onefile --windowed）。

git 下载者不需要自己写打包参数：
    powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
或（已装依赖时）：
    pyinstaller ITA-Maskit.spec
产出 dist/ITA-Maskit.exe。
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# polars（Rust 二进制 + 数据）全量收集，避免运行时报缺文件
polars_datas, polars_binaries, polars_hidden = collect_all("polars")
datas += polars_datas
binaries += polars_binaries
hiddenimports += polars_hidden

# maskit 全部子模块：大量方法内延迟 import（maskit.io.*、maskit.llm、
# maskit.preview、maskit.gui_preview、maskit.rules.matcher 等），
# PyInstaller 静态分析抓不到，必须显式收集
hiddenimports += collect_submodules("maskit")

# 延迟依赖（方法内 import，静态分析抓不到）
hiddenimports += [
    "typer",          # cli（rules generate）
    "yaml",           # 规则 YAML
    "openpyxl",       # Excel
    "xlsxwriter",     # Excel 写出
    "pypdf",          # PDF 读取
    "reportlab",      # PDF 写出
    "docx",           # Word
    "extract_msg",    # Outlook .msg
    "httpx",          # LLM 规则生成（GUI AI 生成）
    "PIL",            # 图片脱敏（beta）
    "pytesseract",    # 图片脱敏（beta，需另装 tesseract 二进制）
]

a = Analysis(
    ["maskit/gui_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除与脱敏无关的重型 ML 库（本机 site-packages 常装有 torch/nvidia 等，
    # PyInstaller 分析依赖会误收进来，导致包体膨胀到数 GB）
    excludes=[
        "torch", "nvidia", "triton", "cuda", "transformers",
        "bitsandbytes", "tensorflow", "keras",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ITA-Maskit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # PyQt5 应用 UPX 易误报且首启动慢，不压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # --windowed：GUI 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
