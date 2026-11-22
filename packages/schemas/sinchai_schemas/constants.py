"""Cited constants loader. Every real-world number in the code base is read through here."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PATH = Path(__file__).with_name("constants.yaml")


@dataclass(frozen=True)
class Constant:
    key: str
    value: Any
    unit: str
    kind: str
    source_url: str | None
    note: str | None


@lru_cache(maxsize=1)
def _load() -> dict[str, Constant]:
    raw = yaml.safe_load(_PATH.read_text())
    sources: dict[str, str] = raw["sources"]
    out: dict[str, Constant] = {}
    for key, c in raw["constants"].items():
        src = c.get("source")
        out[key] = Constant(
            key=key,
            value=c["value"],
            unit=c.get("unit", ""),
            kind=c["kind"],
            source_url=sources[src] if src else None,
            note=c.get("note"),
        )
    return out


def get(key: str) -> Any:
    """Return the value of a constant. Raises KeyError for unknown keys."""
    return _load()[key].value


def entry(key: str) -> Constant:
    return _load()[key]


def all_constants() -> dict[str, Constant]:
    return dict(_load())


def as_json() -> dict[str, dict[str, Any]]:
    return {
        k: {"value": c.value, "unit": c.unit, "kind": c.kind, "source": c.source_url, "note": c.note}
        for k, c in _load().items()
    }
