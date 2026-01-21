from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class HttpCache:
    root: Path

    @staticmethod
    def from_dir(path: str) -> "HttpCache":
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return HttpCache(root=p)

    def _key(self, *, url: str, params: dict[str, Any]) -> str:
        payload = _stable_json({"url": url, "params": params})
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, *, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        key = self._key(url=url, params=params)
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, *, url: str, params: dict[str, Any], value: dict[str, Any]) -> None:
        key = self._key(url=url, params=params)
        path = self.root / f"{key}.json"
        path.write_text(_stable_json(value), encoding="utf-8")

