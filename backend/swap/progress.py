"""Live progress of swap passes, fed by ComfyUI's websocket and shown in the floating queue list.

In memory only: a restart forgets it, and a finished pass clears its entry."""

from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}

_STAGES = {
    "1": "Loading model", "2": "Loading text encoder", "3": "Loading LoRA", "3b": "Loading turbo LoRA", "4": "Loading VAE",
    "5": "Loading VAE", "9": "Reading video", "10": "Reading video", "img0": "Reading reference", "12": "Encoding prompt",
    "13": "Preparing", "14": "Preparing", "15": "Preparing", "16": "Preparing", "17": "Sampling", "18": "Decoding video",
    "20": "Building video", "21": "Saving",
}


def from_message(msg: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    """A ComfyUI websocket message -> {stage, value, max, fraction}, or None when it is not ours or not progress."""
    data = msg.get("data") or {}
    if data.get("prompt_id") != prompt_id:
        return None
    node = data.get("node")
    if msg.get("type") == "progress" and data.get("max"):
        value, mx = int(data.get("value", 0)), int(data["max"])
        return {"stage": _STAGES.get(str(node), "Sampling"), "value": value, "max": mx, "fraction": value / mx}
    if msg.get("type") == "executing" and node is not None:
        return {"stage": _STAGES.get(str(node), "Working"), "value": None, "max": None, "fraction": None}
    return None


def set(pass_id: str, info: dict[str, Any]) -> None:  # noqa: A001 - mirrors get/clear
    with _LOCK:
        _STATE[pass_id] = info


def get(pass_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _STATE.get(pass_id)


def clear(pass_id: str) -> None:
    with _LOCK:
        _STATE.pop(pass_id, None)
