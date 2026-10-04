"""Every finished generation of a clip is kept (its own file plus the settings that made it) so earlier takes can be compared
and brought back. Pure helpers; main.py stores the list on the clip as `history`."""
from __future__ import annotations

import uuid
from typing import Any


def make_entry(output_path: str, settings: dict[str, Any] | None, seconds: float | None, finished_at: float, label: str = "") -> dict[str, Any]:
    s = settings or {}
    return {
        "id": uuid.uuid4().hex[:12],
        "output_path": output_path,
        "finished_at": finished_at,
        "seconds": seconds,
        "seed": s.get("seed"),
        "resolution": s.get("resolution"),
        "steps": s.get("num_inference_steps"),
        "label": label,
        "settings": s,
    }


def add(history: list[dict[str, Any]] | None, entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = list(history or [])
    if any(e["output_path"] == entry["output_path"] for e in out):
        return out
    return [*out, entry]


def find(history: list[dict[str, Any]] | None, entry_id: str) -> dict[str, Any] | None:
    return next((e for e in history or [] if e["id"] == entry_id), None)
