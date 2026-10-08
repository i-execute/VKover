"""Active VK calls cache: no list endpoint exists, so we track locally."""

import time

from .client import VKError


class CallsCache:
    """In-memory registry of started calls (calls.get* does not exist)."""

    def __init__(self, vk, db=None):
        self._vk = vk
        self._db = db
        self._calls: dict[str, dict] = {}

    def add(self, resp: dict) -> dict:
        call_id = (resp.get("call_id") or "").strip()
        if not call_id:
            raise ValueError("no call_id in response")
        entry = {
            "call_id": call_id,
            "join_link": resp.get("join_link", ""),
            "short_credentials": resp.get("short_credentials") or {},
            "created": time.time(),
        }
        self._calls[call_id] = entry
        if self._db is not None:
            self._db.set("vkover.calls", "active", dict(self._calls))
        return entry

    def remove(self, call_id: str) -> dict | None:
        entry = self._calls.pop(call_id, None)
        if entry is not None and self._db is not None:
            self._db.set("vkover.calls", "active", dict(self._calls))
        return entry

    def get(self, call_id: str) -> dict | None:
        return self._calls.get(call_id)

    def all(self) -> list[dict]:
        return list(self._calls.values())

    def finish(self, call_id: str) -> dict | None:
        """Force-finish via API and drop from cache."""
        self._vk.finish_call_request(call_id)
        return self.remove(call_id)

    def load(self) -> None:
        if self._db is not None:
            self._calls = dict(self._db.get("vkover.calls", "active", {}) or {})
