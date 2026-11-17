"""异步图片解析 — 下载远程图片 → 上传飞书 → 替换 URL."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from .html_render import render_html

if TYPE_CHECKING:
    from ..feishu import FeishuClient

_logger = logging.getLogger("hermes_lark_streaming")

# Remote URLs, plus local image files (absolute path or file://) such as screenshots the agent made.
_IMG_PATTERN = re.compile(
    r"!\[.*?\]\((https?://[^\s)]+|(?:file://)?/[^\s)]+\.(?:png|jpe?g|gif|webp|bmp))\)", re.I
)
# Lark cards cannot render HTML: ```html blocks are rendered to an image instead.
_HTML_BLOCK = re.compile(r"```html[ \t]*\n(.*?)```", re.S)
_HTML_OPEN = re.compile(r"```html[ \t]*\n(?:(?!```).)*\Z", re.S)  # still streaming in
_HTML_PLACEHOLDER = "_Rendering HTML…_"


class ImageResolver:
    """解析 markdown 中的图片引用，上传到飞书后替换为 img_key.

    支持同步 strip + 异步上传 + 上传完成回调.
    """

    def __init__(
        self,
        client: FeishuClient,
        timeout: float = 15.0,
        on_image_resolved: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._on_image_resolved = on_image_resolved
        self._cache: dict[str, str] = {}  # url → img_key
        self._pending: dict[str, asyncio.Task[str | None]] = {}  # url → upload task
        self._failed: set[str] = set()  # 已失败的不重试

    def resolve_images(self, text: str, final: bool = False) -> str:
        """同步解析图片：缓存命中替换、新 URL strip 并触发异步上传.

        返回替换后的文本（未完成的 URL 被 strip）.
        """
        if "```html" in text:
            text = self._resolve_html(text, final)
        if "![" not in text:
            return text

        def _replace(m: re.Match[str]) -> str:
            alt = str(m.group(0)).split("](")[0][2:]  # extract alt text
            url = str(m.group(1))

            # 缓存命中
            if url in self._cache:
                return f"![{alt}]({self._cache[url]})"

            # 已失败
            if url in self._failed:
                return ""

            # 正在上传中
            if url in self._pending:
                return ""

            # 新 URL — 启动异步上传，当前帧先 strip
            self._start_upload(url)
            return ""

        return _IMG_PATTERN.sub(_replace, text)

    async def resolve_await(self, text: str) -> str:
        """带超时的批量解析 — 等待所有 pending 上传完成后再替换.

        用于终态卡片构建.
        """
        # 第一遍：触发上传
        self.resolve_images(text)

        if self._pending:
            _logger.info("image_resolver: waiting for %d uploads", len(self._pending))
            tasks = list(self._pending.values())
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self._timeout,
                )
            except TimeoutError:
                _logger.warning("image_resolver: timeout waiting for uploads")

        # 第二遍：替换已完成的
        return self.resolve_images(text, final=True)

    def _resolve_html(self, text: str, final: bool) -> str:
        """```html blocks -> rendered card image (img_key), rendering in the background."""

        def _replace(m: re.Match[str]) -> str:
            html = m.group(1)
            key = "html:" + hashlib.sha1(html.encode("utf-8")).hexdigest()
            if key in self._cache:
                return f"![HTML]({self._cache[key]})"
            if key in self._failed:
                return m.group(0)  # render failed: show the source rather than lose it
            if key not in self._pending:
                self._start_html_render(key, html)
            return "" if final else _HTML_PLACEHOLDER

        text = _HTML_BLOCK.sub(_replace, text)
        if not final:
            text = _HTML_OPEN.sub(_HTML_PLACEHOLDER, text)
        return text

    def _start_html_render(self, key: str, html: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._pending[key] = loop.create_task(self._do_html_render(key, html))

    async def _do_html_render(self, key: str, html: str) -> str | None:
        try:
            png = await render_html(html)
            img_key = await self._client.upload_image_bytes(png) if png else None
            if img_key:
                self._cache[key] = img_key
                _logger.info("image_resolver: rendered html -> %s", img_key)
                if self._on_image_resolved:
                    self._on_image_resolved()
                return img_key
            self._failed.add(key)
            return None
        except Exception as exc:
            _logger.debug("image_resolver: html render failed: %s", exc, exc_info=True)
            self._failed.add(key)
            return None
        finally:
            self._pending.pop(key, None)

    def cancel_pending(self) -> None:
        """取消所有正在进行的上传任务（用于 session 清理）."""
        for task in self._pending.values():
            task.cancel()
        self._pending.clear()

    def _start_upload(self, url: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._do_upload(url))
        self._pending[url] = task

    async def _do_upload(self, url: str) -> str | None:
        try:
            img_key = await self._client.upload_image(url)
            if img_key:
                self._cache[url] = img_key
                _logger.info("image_resolver: uploaded %s -> %s", url, img_key)
                if self._on_image_resolved:
                    self._on_image_resolved()
                return img_key
            self._failed.add(url)
            return None
        except Exception as exc:
            _logger.debug("image_resolver: upload failed for %s: %s", url, exc, exc_info=True)
            self._failed.add(url)
            return None
        finally:
            self._pending.pop(url, None)
