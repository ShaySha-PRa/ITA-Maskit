"""Build short looping GIFs for the README (CLI + GUI).

    python scripts/gen_demo_videos.py

Needs Pillow and ffmpeg. Output: assets/demo/cli.gif, assets/demo/gui.gif
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "assets" / "screenshots"
OUT = ROOT / "assets" / "demo"
FFMPEG = shutil.which("ffmpeg") or (
    r"C:\Users\Joshu\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
)
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]
SYMBOL_CANDIDATES = [
    Path(r"C:\Windows\Fonts\seguisym.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def _symbol_font(size: int) -> ImageFont.ImageFont:
    for path in SYMBOL_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return _font(size)


def _draw_text(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: str, font) -> None:
    """YaHei has no U+2713; draw the CLI check with a symbol font."""
    if text.startswith("✓"):
        sym = _symbol_font(getattr(font, "size", 16))
        d.text(xy, "✓", fill=fill, font=sym)
        pad = int(d.textlength("✓ ", font=sym))
        d.text((xy[0] + pad, xy[1]), text[1:].lstrip(), fill=fill, font=font)
        return
    d.text(xy, text, fill=fill, font=font)


def _encode_gif(frames_dir: Path, dest: Path, fps: int = 8) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "f_%04d.png")
    palette = frames_dir / "palette.png"
    vf = f"fps={fps},scale=720:-1:flags=lanczos"
    subprocess.run(
        [FFMPEG, "-y", "-i", pattern, "-vf", f"{vf},palettegen=stats_mode=diff", str(palette)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            FFMPEG, "-y", "-framerate", str(fps), "-i", pattern, "-i", str(palette),
            "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
            "-loop", "0", str(dest),
        ],
        check=True,
        capture_output=True,
    )


def _save(draw_fn, index: int, folder: Path) -> None:
    img = draw_fn()
    img.save(folder / f"f_{index:04d}.png")


def _cli_frames(folder: Path) -> None:
    w, h = 880, 400
    bg, fg, dim, ok, cmd = "#1e1e1e", "#f3f3f3", "#9aa0a6", "#3dd68c", "#79c0ff"
    title = _font(18)
    body = _font(16)
    lines_final = [
        (dim, "$ "),
        (cmd, "maskit demo --rows 100000"),
        (ok, "✓ 已生成演示数据 100000 行 → demo_data.csv"),
        (dim, "$ "),
        (cmd, "maskit mask demo_data.csv --rules demo-rules.yaml --pepper <密钥> -o out.csv"),
        (ok, "✓ 已脱敏 100000 项 → out.csv"),
        (dim, "$ "),
        (cmd, "maskit audit"),
        (fg, "  2026-08-23T05:12:00  demo_data.csv  rows=100000  rules=1.0"),
        (dim, "  [mask:name,ip  pseudo:phone,email]  pepper=a1b2c3d4…"),
    ]

    typed = [
        "maskit demo --rows 100000",
        "maskit mask demo_data.csv --rules demo-rules.yaml --pepper <密钥> -o out.csv",
        "maskit audit",
    ]

    def paint(shown: list[tuple[str, str]]) -> Image.Image:
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w, 36), fill="#2d2d2d")
        d.text((16, 8), "ITA-maskit  ·  命令行", fill=fg, font=title)
        y = 56
        for color, text in shown:
            _draw_text(d, (20, y), text, color, body)
            y += 30
        return img

    n = 0
    shown: list[tuple[str, str]] = []
    cmd_i = 0
    for color, text in lines_final:
        if color == cmd:
            prefix = shown + [(dim, "$ ")]
            for i in range(1, len(typed[cmd_i]) + 1):
                _save(lambda t=typed[cmd_i][:i], p=prefix: paint(p + [(cmd, t)]), n, folder)
                n += 1
            shown.append((dim, "$ "))
            shown.append((cmd, typed[cmd_i]))
            cmd_i += 1
            continue
        if color == dim and text == "$ ":
            continue
        shown.append((color, text))
        for _ in range(3):
            _save(lambda s=list(shown): paint(s), n, folder)
            n += 1
    for _ in range(10):
        _save(lambda s=list(shown): paint(s), n, folder)
        n += 1


def _fit(img: Image.Image, box: tuple[int, int], fill: str) -> Image.Image:
    canvas = Image.new("RGB", box, fill)
    img = img.convert("RGB")
    img.thumbnail((box[0] - 24, box[1] - 56), Image.Resampling.LANCZOS)
    x = (box[0] - img.width) // 2
    y = 12
    canvas.paste(img, (x, y))
    return canvas


def _gui_frames(folder: Path) -> None:
    w, h = 900, 720
    caption_font = _font(20)
    scenes = [
        (SHOTS / "main.png", "1 / 3  选择文件 → 预验证 → 开始脱敏"),
        (SHOTS / "preview.png", "2 / 3  预验证：绿=将脱敏，黄=该列未命中"),
        (SHOTS / "rules.png", "3 / 3  规则管理：描述代替正则，可导入导出"),
    ]
    n = 0
    for path, caption in scenes:
        base = _fit(Image.open(path), (w, h), "#f4f6f8")
        d = ImageDraw.Draw(base)
        d.rectangle((0, h - 44, w, h), fill="#1f4b99")
        d.text((20, h - 34), caption, fill="white", font=caption_font)
        for _ in range(18):
            base.save(folder / f"f_{n:04d}.png")
            n += 1


def main() -> None:
    if not Path(FFMPEG).exists():
        raise SystemExit("ffmpeg not found")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cli_dir = Path(tmp) / "cli"
        gui_dir = Path(tmp) / "gui"
        cli_dir.mkdir()
        gui_dir.mkdir()
        _cli_frames(cli_dir)
        _gui_frames(gui_dir)
        _encode_gif(cli_dir, OUT / "cli.gif", fps=10)
        _encode_gif(gui_dir, OUT / "gui.gif", fps=8)
    for name in ("cli.gif", "gui.gif"):
        p = OUT / name
        print(f"{p}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
