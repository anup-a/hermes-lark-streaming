"""Render an HTML snippet to a PNG so it can sit inside a Lark card.

Lark cards have no HTML/webview component, so ```html blocks in the agent's answer are
rendered by headless Chromium (JS runs, so canvas/SVG charts work), trimmed to the content
height, and uploaded as a card image. Theme variables and layout rules follow T3 Code's
html_render (light theme) so pages written for T3 look the same here.

Also a CLI for checking a page before sending it (like T3's html_preview):
    python -m hermes_lark_streaming.streaming.html_render page.html [out.png]
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger("hermes_lark_streaming")

WIDTH = 728  # CSS px, T3's reply column width; fits a Lark card on desktop
MAX_HEIGHT = 4000  # CSS px; longer pages are cut
SCALE = 2  # retina-sharp image
JS_BUDGET_MS = 2500  # virtual time for scripts/charts to settle
TIMEOUT_S = 25

# T3 Code light theme (packages/shared/src/htmlRender.ts + themePalettes.ts), on a white card.
THEME_VARS = {
    "--background": "#ffffff", "--foreground": "#27272a",
    "--muted": "#fafafa", "--muted-foreground": "#71717b",
    "--card": "#ffffff", "--card-foreground": "#27272a",
    "--popover": "#ffffff", "--popover-foreground": "#27272a",
    "--secondary": "#fafafa", "--secondary-foreground": "#27272a",
    "--border": "#e4e4e7", "--input": "#d4d4d8", "--ring": "#1b4ed8",
    "--primary": "#1b4ed8", "--primary-foreground": "#ffffff",
    "--accent": "#1b4ed8", "--accent-foreground": "#ffffff",
    "--accent-surface": "#f4f4f5", "--accent-surface-foreground": "#18181b",
    "--destructive": "#fb2c36", "--destructive-foreground": "#c10007", "--destructive-surface": "#fcebec",
    "--warning": "#fe9a00", "--warning-foreground": "#bb4d00", "--warning-surface": "#fcf4e8",
    "--success": "#10b981", "--success-foreground": "#047857",
    "--info": "#3b82f6", "--info-foreground": "#1d4ed8",
    "--code-background": "#f4f4f5", "--code-foreground": "#27272a",
    "--chart-1": "#1b4ed8", "--chart-2": "#0d9488", "--chart-3": "#d97706",
    "--chart-4": "#9333ea", "--chart-5": "#e11d48", "--chart-6": "#65a30d",
    "--radius": "0.625rem",
    "--font-sans": (
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif'
    ),
    "--font-mono": '"SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
}
_BASE_CSS = (
    ":root{" + ";".join(f"{k}:{v}" for k, v in THEME_VARS.items()) + "}"
    "html{padding:8px;background:var(--background)}"
    "body{margin:0;color:var(--foreground);font:15px/1.5 var(--font-sans)}"
)
_HEAD = f'<meta charset="utf-8"><style>{_BASE_CSS}</style>'
# Same check as T3: vh units make a page grow with its frame forever.
_VIEWPORT_HEIGHT = re.compile(r"(?<![\w.+/])(?:\d+(?:\.\d+)?|\.\d+)[sld]?vh(?![\w-])", re.I)
_CONSOLE = re.compile(r'CONSOLE\(\d+\)\] "(.*)", source:|:CONSOLE:?\d*\] "?(.*?)"?, source')


@dataclass(frozen=True)
class RenderResult:
    png: bytes | None
    content_height: int  # CSS px of the trimmed page
    console: tuple[str, ...]
    warnings: tuple[str, ...]


def _chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _document(html: str) -> str:
    """Base sheet goes first so the page's own CSS can override it."""
    if "<html" not in html.lower():
        return f"<!doctype html><html><head>{_HEAD}</head><body>{html}</body></html>"
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + _HEAD, html, count=1, flags=re.I)
    return re.sub(r"(<html[^>]*>)", lambda m: m.group(1) + f"<head>{_HEAD}</head>", html, count=1, flags=re.I)


def _trim(png: bytes) -> tuple[bytes, int]:
    """Crop the empty area below the content (the window is taller than the page)."""
    from PIL import Image, ImageChops

    img = Image.open(io.BytesIO(png)).convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((img.width - 1, img.height - 1)))
    box = ImageChops.difference(img, bg).getbbox()
    if box:
        img = img.crop((0, 0, img.width, min(img.height, box[3] + 8 * SCALE)))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue(), round(img.height / SCALE)


def render_page(html: str) -> RenderResult:
    warnings = []
    if _VIEWPORT_HEIGHT.search(html):
        warnings.append("uses vh units: use fixed pixel heights instead")
    if re.search(r"""(?:src|href)\s*=\s*["']https?://""", html, re.I):
        warnings.append("loads remote files: inline them so the render does not depend on the network")
    exe = _chromium()
    if exe is None:
        return RenderResult(None, 0, (), (*warnings, "no chromium on PATH"))
    with tempfile.TemporaryDirectory(prefix="lark-html-") as tmp:
        page, shot = os.path.join(tmp, "page.html"), os.path.join(tmp, "shot.png")
        with open(page, "w", encoding="utf-8") as f:
            f.write(_document(html))
        cmd = [
            exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--enable-logging=stderr", "--v=0", "--allow-file-access-from-files",
            f"--user-data-dir={tmp}/profile", f"--force-device-scale-factor={SCALE}",
            f"--window-size={WIDTH},{MAX_HEIGHT}", f"--virtual-time-budget={JS_BUDGET_MS}",
            f"--screenshot={shot}", f"file://{page}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            return RenderResult(None, 0, (), (*warnings, "chromium timed out"))
        console = tuple(next(g for g in m.groups() if g) for m in _CONSOLE.finditer(proc.stderr or ""))
        if not os.path.exists(shot):
            return RenderResult(None, 0, console, (*warnings, "chromium produced no screenshot"))
        with open(shot, "rb") as f:
            png, height = _trim(f.read())
    if height >= MAX_HEIGHT - 10:
        warnings.append(f"page is taller than {MAX_HEIGHT}px and was cut: split it")
    return RenderResult(png, height, console, tuple(warnings))


async def render_html(html: str) -> bytes | None:
    try:
        result = await asyncio.get_running_loop().run_in_executor(None, render_page, html)
    except Exception:
        _logger.warning("html_render: render failed", exc_info=True)
        return None
    for note in (*result.warnings, *result.console):
        _logger.info("html_render: %s", note)
    return result.png


def main() -> int:
    """html-preview: render a page the way a card will show it, report height, console, warnings."""
    if len(sys.argv) < 2:
        print("usage: html-preview <page.html|-> [out.png]", file=sys.stderr)
        return 2
    src = sys.argv[1]
    html = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(), "html-preview.png")
    result = render_page(html)
    if result.png:
        with open(out, "wb") as f:
            f.write(result.png)
    print(json.dumps({
        "png": out if result.png else None, "width": WIDTH, "contentHeight": result.content_height,
        "console": list(result.console), "warnings": list(result.warnings),
    }, ensure_ascii=False, indent=1))
    return 0 if result.png else 1


if __name__ == "__main__":
    sys.exit(main())
