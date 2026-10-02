"""Upscale (or refine) the result of a pass with one of WanGP's post-processors (FlashVSR, SeedVR2, the H3 face refiner, ...).

The upscaled clip is added to the pass's history as its own run; the result in use does not change, so it can be compared first."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2

from . import runner


def build_wangp_settings(media: str, process_id: str, multiplier: float) -> dict[str, Any]:
    """The job settings WanGP needs for a spatial post-processing of `media` (needs the WanGP modules the backend loads)."""
    from postprocessing import catalog  # noqa: WPS433
    from shared.api import build_media_postprocessing_settings  # noqa: WPS433

    process = catalog.find_processes("video", process_id)[0]
    value = catalog.build_process_value(process, {"multiplier": multiplier})
    return build_media_postprocessing_settings(media, spatial_upsampling=value)


def start(project_id: str, pass_id: str, *, store_mod: Any, job_store: Any, process_id: str, multiplier: float = 2.0,
          build_settings: Callable[[str, str, float], dict[str, Any]] = build_wangp_settings) -> None:
    project = store_mod.find(project_id)
    pass_ = next(p for p in project["passes"] if p["id"] == pass_id)
    media = pass_["output_path"]
    run_id = uuid.uuid4().hex[:8]
    dest = Path(store_mod.project_dir(project)) / "passes" / f"{pass_id}_{run_id}_{process_id}.mp4"
    t0 = time.time()
    before = pass_.get("status") or "done"
    base = next((h for h in pass_.get("history") or [] if h.get("output_path") == media), None) or {}

    def restore(**fields: Any) -> None:
        store_mod.update_pass(project_id, pass_id, status=before, job_id=None, **fields)

    def queued(job_id: str) -> None:
        store_mod.update_pass(project_id, pass_id, status="queued", job_id=job_id, upscale_error=None)

    def running() -> None:
        store_mod.update_pass(project_id, pass_id, status="running")

    def done(status: str, output_path: Any = None, error: str | None = None, duration_seconds: float | None = None) -> None:
        if status != "done":
            return restore(upscale_error=error or "upscaling failed")
        cap = cv2.VideoCapture(str(dest))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        entry = {**{k: v for k, v in base.items() if k not in ("id", "created_at", "output_path", "method", "edited_frame")},
                 "id": run_id, "created_at": time.time(), "output_path": str(dest), "method": "upscale", "process": process_id,
                 "multiplier": multiplier, "width": width, "height": height, "seconds": round(time.time() - t0, 1),
                 "mean_luma": round(runner.mean_luma(str(dest)), 1), "raw_path": pass_.get("raw_path") or base.get("raw_path")}
        history = list(next((p for p in store_mod.find(project_id)["passes"] if p["id"] == pass_id), {}).get("history") or []) + [entry]
        restore(history=history, upscale_error=None)

    job_store.submit(build_settings(media, process_id, multiplier), dest, done, on_queued=queued, on_running=running)
