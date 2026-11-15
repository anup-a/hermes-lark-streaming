"""Render an HTML snippet to a PNG so it can sit inside a Lark card.

Lark cards have no HTML/webview component, so ```html blocks in the agent's answer are
rendered by headless Chromium (JS runs, so canvas/SVG charts work), trimmed to the content
height, and uploaded as a card image.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import tempfile

_logger = logging.getLogger("hermes_lark_streaming")

WIDTH = 760  # CSS px; Lark card content width on desktop is about this
MAX_HEIGHT = 4000  # CSS px; longer pages are cut
SCALE = 2  # retina-sharp image
JS_BUDGET_MS = 2500  # virtual time for scripts/charts to settle
TIMEOUT_S = 25

_WRAPPER = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#fff}}body{{padding:16px;font:15px/1.5 -apple-system,
"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif;color:#1f2329}}</style></head>
<body>{body}</body></html>"""


def _chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _wrap(html: str) -> str:
    return html if "<html" in html.lower() else _WRAPPER.format(body=html)


def _trim(png: bytes) -> bytes:
    """Crop the empty area below the content (window is taller than the page)."""
    from PIL import Image, ImageChops

    img = Image.open(io.BytesIO(png)).convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((img.width - 1, img.height - 1)))
    box = ImageChops.difference(img, bg).getbbox()
    if box:
        pad = 16 * SCALE
        img = img.crop((0, 0, img.width, min(img.height, box[3] + pad)))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _render_sync(html: str) -> bytes | None:
    exe = _chromium()
    if exe is None:
        _logger.warning("html_render: no chromium on PATH")
        return None
    with tempfile.TemporaryDirectory(prefix="lark-html-") as tmp:
        page, shot = os.path.join(tmp, "page.html"), os.path.join(tmp, "shot.png")
        with open(page, "w", encoding="utf-8") as f:
            f.write(_wrap(html))
        import subprocess

        cmd = [
            exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            f"--user-data-dir={tmp}/profile", f"--force-device-scale-factor={SCALE}",
            f"--window-size={WIDTH},{MAX_HEIGHT}", f"--virtual-time-budget={JS_BUDGET_MS}",
            f"--screenshot={shot}", f"file://{page}",
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            _logger.warning("html_render: chromium timed out")
            return None
        if not os.path.exists(shot):
            _logger.warning("html_render: chromium produced no screenshot")
            return None
        with open(shot, "rb") as f:
            return _trim(f.read())


async def render_html(html: str) -> bytes | None:
    try:
        return await asyncio.get_running_loop().run_in_executor(None, _render_sync, html)
    except Exception:
        _logger.warning("html_render: render failed", exc_info=True)
        return None
