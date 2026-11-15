"""仍在流式中的卡片登记表（落盘），用于网关重启后收尾遗留的「处理中」卡片.

思路来自 wzgrx/hermes-lark-streaming 的 open_cards。卡片创建时登记，完成后移除；
流式期间定期保存一份「已中断」形态的完整卡片快照。网关被杀或崩溃后，下一个网关
用快照整卡更新，保留已显示的内容并标记为已中断。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger("hermes_lark_streaming")

OPEN_CARDS_FILE = "hermes-lark-streaming-open-cards.json"
MAX_ENTRIES = 64


class OpenCards:
    """只由网关进程读写；任何失败只记日志，不抛出."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            _logger.warning("open card registry unreadable; starting empty", exc_info=True)
            return {}
        cards = raw.get("cards") if isinstance(raw, dict) else None
        if not isinstance(cards, dict):
            return {}
        return {str(k): v for k, v in cards.items() if isinstance(v, dict)}

    def _write(self, cards: dict[str, dict[str, Any]]) -> None:
        kept = dict(sorted(cards.items(), key=lambda kv: kv[1].get("opened_at", 0), reverse=True)[:MAX_ENTRIES])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f"{self.path.suffix}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps({"cards": kept}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def _mutate(self, change: Any) -> None:
        try:
            with self._lock:
                cards = self._read()
                if change(cards):
                    self._write(cards)
        except Exception:
            _logger.warning("open card registry write failed", exc_info=True)

    def add(self, card_id: str, chat_id: str, message_id: str) -> None:
        def change(cards: dict[str, dict[str, Any]]) -> bool:
            if not card_id or card_id in cards:
                return False
            cards[card_id] = {"chat_id": chat_id, "message_id": message_id, "opened_at": time.time(), "attempts": 0}
            return True

        self._mutate(change)

    def save_snapshot(self, card_id: str, card: dict[str, Any]) -> None:
        def change(cards: dict[str, dict[str, Any]]) -> bool:
            if card_id not in cards:
                return False
            cards[card_id]["snapshot"] = card
            return True

        self._mutate(change)

    def remove(self, card_id: str) -> None:
        self._mutate(lambda cards: cards.pop(card_id, None) is not None)

    def attempted(self, card_id: str, *, give_up_after: int = 3) -> None:
        def change(cards: dict[str, dict[str, Any]]) -> bool:
            entry = cards.get(card_id)
            if entry is None:
                return False
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            if entry["attempts"] >= give_up_after:
                del cards[card_id]
            return True

        self._mutate(change)

    def orphans(self, live: set[str], *, min_age: float) -> list[tuple[str, dict[str, Any]]]:
        """登记过、不属于当前进程任何回合、且超过 min_age 秒的卡片."""
        try:
            with self._lock:
                now = time.time()
                return [
                    (card_id, entry)
                    for card_id, entry in self._read().items()
                    if card_id not in live and now - float(entry.get("opened_at", 0)) >= min_age
                ]
        except Exception:
            _logger.warning("open card registry read failed", exc_info=True)
            return []
