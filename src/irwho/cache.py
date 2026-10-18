"""Tiny thread-safe JSON cache so interrupted scans can resume."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Union

from .models import Status

_VERSION = 1
_CACHED_STATUSES = (Status.AVAILABLE.value, Status.TAKEN.value, Status.UNKNOWN.value)


class Cache:
    """Maps domain -> :class:`Status`, persisted as JSON on disk."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, object]] = self._load()

    def _load(self) -> Dict[str, Dict[str, object]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != _VERSION:
            return {}
        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            return {}
        return {
            key: value
            for key, value in entries.items()
            if isinstance(value, dict) and value.get("status") in _CACHED_STATUSES
        }

    def get(self, domain: str) -> Optional[Status]:
        with self._lock:
            entry = self._data.get(domain.lower())
        return Status(str(entry["status"])) if entry else None

    def put(self, domain: str, status: Status) -> None:
        if status is Status.ERROR:
            return  # never cache failures, they are usually transient
        with self._lock:
            self._data[domain.lower()] = {"status": str(status), "ts": int(time.time())}
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._save()

    def prune(self, max_age: int = 7 * 24 * 3600) -> int:
        """Drop entries older than ``max_age`` seconds. Returns how many."""
        cutoff = int(time.time()) - max_age
        with self._lock:
            stale = [k for k, v in self._data.items() if int(v.get("ts", 0)) < cutoff]
            for key in stale:
                del self._data[key]
            if stale:
                self._save()
        return len(stale)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            payload = {"version": _VERSION, "entries": self._data}
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # a broken cache file must never break a scan

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
