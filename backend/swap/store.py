"""Swap projects on disk.

Layout: data/swaps/<slug>-<id8>/config.json plus source/, passes/, final/, thumbs/. One RLock guards
every read-modify-write so the job watcher threads and HTTP handlers never race each other.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from . import prompts, scenes as scenes_mod

ROOT = Path(__file__).resolve().parent.parent / "data" / "swaps"
_LOCK = threading.RLock()
SUBDIRS = ("source", "passes", "final", "thumbs")


class NotFound(Exception):
    pass


def _slug(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "swap")[:40]


def project_dir(project: dict[str, Any]) -> Path:
    return ROOT / project["folder"]


def _config(project: dict[str, Any]) -> Path:
    return project_dir(project) / "config.json"


def new_project(title: str, source_info: dict[str, Any]) -> dict[str, Any]:
    pid = uuid.uuid4().hex
    project = {
        "id": pid, "title": title or "Swap", "created_at": time.time(), "folder": f"{_slug(title)}-{pid[:8]}",
        "status": "draft", "source": dict(source_info),
        "settings": {"quality": "final", "width": 704, "height": 1248, "seed": 904234,
                     "chunk_max_final": 243, "chunk_max_preview": 124},
        "cast": [], "scenes": [], "scenes_confirmed": False, "passes": [], "final": {"path": None, "status": "none", "error": None}, "plan_notes": [],
    }
    with _LOCK:
        for sub in SUBDIRS:
            (project_dir(project) / sub).mkdir(parents=True, exist_ok=True)
        save(project)
    return project


def save(project: dict[str, Any]) -> None:
    with _LOCK:
        path = _config(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(project, indent=2), encoding="utf-8")
        tmp.replace(path)


def load_all() -> list[dict[str, Any]]:
    with _LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        out = []
        for entry in ROOT.iterdir():
            cfg = entry / "config.json"
            if entry.is_dir() and cfg.exists():
                try:
                    out.append(_migrate(json.loads(cfg.read_text(encoding="utf-8"))))
                except json.JSONDecodeError:
                    continue
        out.sort(key=lambda p: p.get("created_at", 0), reverse=True)
        return out


def _migrate(project: dict[str, Any]) -> dict[str, Any]:
    """Chunks planned before the 124-frame minimum carry their old padded length; bring them up to date on read."""
    if "scenes_confirmed" not in project:  # projects from before the cuts had to be confirmed: confirmed when they already have work
        project["scenes_confirmed"] = bool(project.get("scenes") and (project.get("cast") or project.get("passes")))
    for scene in project.get("scenes", []):
        for chunk in scene.get("chunks", []):
            chunk["padded_frames"] = scenes_mod.render_length(chunk["frames_24"])
    return project


def find(project_id: str) -> dict[str, Any]:
    for p in load_all():
        if p["id"] == project_id:
            return p
    raise NotFound(project_id)


def update(project_id: str, fn: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    with _LOCK:
        project = find(project_id)
        fn(project)
        save(project)
        return project


def delete(project_id: str) -> None:
    with _LOCK:
        project = find(project_id)
        shutil.rmtree(project_dir(project), ignore_errors=True)


def set_scenes(project: dict[str, Any], scene_list: list[dict[str, Any]]) -> None:
    """Replace the scenes (fresh detection). Everything planned from the old scenes is dropped."""
    project["scenes"] = [{**s, "background_text": s.get("background_text", ""), "people": s.get("people", [])} for s in scene_list]
    project["passes"] = []
    project["plan_notes"] = []
    project["scenes_confirmed"] = False


def build_plan(project: dict[str, Any]) -> dict[str, Any]:
    """Returns a copy with `passes` rebuilt: per scene with people, per chunk, per person in order."""
    out = copy.deepcopy(project)
    cast = {c["id"]: c for c in out["cast"]}
    quality = out["settings"]["quality"]
    passes: list[dict[str, Any]] = []
    notes: list[str] = []
    for scene in out["scenes"]:
        people = sorted(scene.get("people") or [], key=lambda p: p["order"])
        if not people:
            notes.append(f"Scene {scene['index'] + 1} has no people assigned and was skipped.")
            continue
        for chunk in scene["chunks"]:
            for person in people:
                entry: dict[str, Any] = {
                    "id": uuid.uuid4().hex, "scene_index": scene["index"], "chunk_index": chunk["index"],
                    "person_id": person["id"], "order": person["order"], "quality": quality, "prompt": "",
                    "status": "draft", "job_id": None, "output_path": None, "raw_path": None, "mean_luma": None,
                    "error": None, "seconds": None, "width": None, "height": None, "seed": None, "history": [],
                }
                try:
                    entry["prompt"] = prompts.build_pass_prompt(person, cast, people, scene.get("background_text", ""))
                except prompts.PromptError as exc:
                    entry["status"] = "blocked"
                    entry["error"] = str(exc)
                passes.append(entry)
    out["passes"] = passes
    out["plan_notes"] = notes
    return out


class Busy(Exception):
    """A scene's passes are queued or running, so it cannot be re-planned."""


def replan_scenes(project: dict[str, Any], indexes: list[int]) -> None:
    """Re-plans only these scenes (fresh prompts and passes, the runs already made stay in their history); every other
    scene keeps its passes, results and edited prompts. People with no character chosen yet are not planned."""
    wanted = set(indexes)
    old = [p for p in project["passes"] if p["scene_index"] in wanted]
    if any(p["status"] in ("queued", "running") for p in old):
        raise Busy(", ".join(str(i + 1) for i in sorted({p["scene_index"] for p in old if p["status"] in ("queued", "running")})))
    trial = copy.deepcopy(project)
    for scene in trial["scenes"]:
        scene["people"] = [x for x in scene.get("people") or [] if x.get("cast_id")]
    planned = build_plan(trial)
    fresh = [p for p in planned["passes"] if p["scene_index"] in wanted]
    carry_history(old, fresh)
    project["passes"] = sorted([p for p in project["passes"] if p["scene_index"] not in wanted] + fresh,
                               key=lambda x: (x["scene_index"], x["chunk_index"], x["order"]))
    project["plan_notes"] = planned["plan_notes"]


def update_pass(project_id: str, pass_id: str, **fields: Any) -> dict[str, Any]:
    def apply(project: dict[str, Any]) -> None:
        for p in project["passes"]:
            if p["id"] == pass_id:
                p.update(fields)
                return
        raise NotFound(pass_id)

    return update(project_id, apply)


_AREA = 704 * 1248  # the resolution ceiling that worked for the swap LoRA (~0.88 MP)


def default_size(src_w: int, src_h: int) -> tuple[int, int]:
    """Render size with the source's aspect, multiples of 32, about _AREA pixels."""
    ar = max(1, src_w) / max(1, src_h)
    h = max(32, round((_AREA / ar) ** 0.5 / 32) * 32)
    w = max(32, round(h * ar / 32) * 32)
    return w, h


def rechunk(project: dict[str, Any]) -> None:
    """Recompute every scene's chunks for the project's current quality (preview chunks are shorter)."""
    s = project["settings"]
    max_chunk = s["chunk_max_preview"] if s["quality"] == "preview" else s["chunk_max_final"]
    for scene in project["scenes"]:
        scene["chunks"] = [{"index": i, "start": a, "end": b, "frames_24": b - a + 1, "padded_frames": scenes_mod.render_length(b - a + 1)}
                           for i, (a, b) in enumerate(scenes_mod.split_chunks(scene["frames_24"], max_chunk))]


def size_for_short_side(src_w: int, src_h: int, short: int) -> tuple[int, int]:
    """Render size whose shorter side is `short` (rounded to 32) keeping the source's aspect."""
    short = max(32, round(short / 32) * 32)
    ar = max(1, src_w) / max(1, src_h)
    if ar >= 1:
        return max(32, round(short * ar / 32) * 32), short
    return short, max(32, round(short / ar / 32) * 32)


def legacy_entry(p: dict[str, Any]) -> dict[str, Any] | None:
    """A history entry for a result made before runs were recorded (it has no entry of its own)."""
    if p.get("status") != "done" or not p.get("output_path"):
        return None
    try:
        made = Path(p["output_path"]).stat().st_mtime
    except OSError:
        made = 0.0
    return {"id": "legacy", "created_at": made, "quality": p.get("quality"), "width": p.get("width"), "height": p.get("height"),
            "seed": p.get("seed"), "seconds": p.get("seconds"), "mean_luma": p.get("mean_luma"), "output_path": p["output_path"],
            "raw_path": p.get("raw_path"), "prompt": p.get("prompt")}


def ensure_history(p: dict[str, Any]) -> None:
    """Persist the legacy entry before a result is about to be cleared, so it stays in the list."""
    if not p.get("history"):
        entry = legacy_entry(p)
        p["history"] = [entry] if entry else []


def carry_history(old_passes: list[dict[str, Any]], new_passes: list[dict[str, Any]]) -> None:
    """A re-plan builds fresh passes; the runs already made for the same (scene, chunk, person order) stay listed."""
    for p in old_passes:
        ensure_history(p)
    kept = {(p["scene_index"], p["chunk_index"], p["order"]): p.get("history") or [] for p in old_passes}
    for p in new_passes:
        p["history"] = list(kept.get((p["scene_index"], p["chunk_index"], p["order"]), []))
