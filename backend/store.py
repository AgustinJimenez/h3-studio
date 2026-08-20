"""Per-video-folder datastore for videos/clips.

Layout: data/videos/<slug>-<id8>/config.json holds one video's full record
(including its clips list); data/videos/<slug>-<id8>/clips/<clip_id>.mp4
holds that video's generated clip files. One lock guards every
read-modify-write so the generation watcher thread and HTTP request
handlers never race each other.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

VIDEOS_ROOT = Path(__file__).resolve().parent / "data" / "videos"
PROMPT_TAGS_PATH = Path(__file__).resolve().parent / "data" / "prompt_tags.json"
ANIMATE_JOBS_PATH = Path(__file__).resolve().parent / "data" / "animate_jobs.json"
ANIMATE_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "animate_jobs"
_LOCK = threading.RLock()


def new_id() -> str:
    return uuid.uuid4().hex


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug or "video")[:40]


def folder_name_for(video_id: str, title: str) -> str:
    return f"{slugify(title)}-{video_id[:8]}"


def video_dir(folder: str) -> Path:
    return VIDEOS_ROOT / folder


def clips_dir(folder: str) -> Path:
    return video_dir(folder) / "clips"


def characters_dir(folder: str) -> Path:
    return video_dir(folder) / "characters"


def config_path(folder: str) -> Path:
    return video_dir(folder) / "config.json"


class NotFound(Exception):
    pass


def _read_all() -> dict[str, Any]:
    VIDEOS_ROOT.mkdir(parents=True, exist_ok=True)
    videos = []
    for entry in sorted(VIDEOS_ROOT.iterdir()):
        cfg = entry / "config.json"
        if entry.is_dir() and cfg.exists():
            try:
                videos.append(json.loads(cfg.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return {"videos": videos}


def _write_video(video: dict[str, Any]) -> None:
    folder = video["folder"]
    video_dir(folder).mkdir(parents=True, exist_ok=True)
    clips_dir(folder).mkdir(parents=True, exist_ok=True)
    config_path(folder).write_text(json.dumps(video, indent=2, ensure_ascii=False), encoding="utf-8")


def load() -> dict[str, Any]:
    with _LOCK:
        return _read_all()


def mutate(fn: Callable[[dict[str, Any]], Any]) -> Any:
    """Read every video, run fn(data) which mutates data['videos'] in
    place, persist every remaining video back to its own config.json,
    return fn's result. Cheap at the scale this app operates at."""
    with _LOCK:
        data = _read_all()
        result = fn(data)
        for video in data["videos"]:
            _write_video(video)
        return result


def create_video(title: str, template_settings: dict[str, Any], base_prompt: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        video_id = new_id()
        video = {
            "id": video_id,
            "folder": folder_name_for(video_id, title),
            "title": title,
            "template_settings": template_settings,
            "base_prompt": base_prompt,
            "characters": [],
            "clips": [],
            "concat_output_path": None,
        }
        _write_video(video)
        return video


def remove_video(video_id: str) -> None:
    with _LOCK:
        data = _read_all()
        video = next((v for v in data["videos"] if v["id"] == video_id), None)
        if video is None:
            raise NotFound(video_id)
        folder_path = video_dir(video["folder"])
        if folder_path.exists():
            shutil.rmtree(folder_path)


def find_video(data: dict[str, Any], video_id: str) -> dict[str, Any]:
    for video in data["videos"]:
        if video["id"] == video_id:
            return video
    raise NotFound(f"video {video_id} not found")


def find_clip(video: dict[str, Any], clip_id: str) -> dict[str, Any]:
    for clip in video["clips"]:
        if clip["id"] == clip_id:
            return clip
    raise NotFound(f"clip {clip_id} not found")


def find_clip_anywhere(data: dict[str, Any], clip_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for video in data["videos"]:
        for clip in video["clips"]:
            if clip["id"] == clip_id:
                return video, clip
    raise NotFound(f"clip {clip_id} not found")


def find_character(video: dict[str, Any], character_id: str) -> dict[str, Any]:
    for character in video.get("characters") or []:
        if character["id"] == character_id:
            return character
    raise NotFound(f"character {character_id} not found")


def find_reference(character: dict[str, Any], reference_id: str) -> dict[str, Any]:
    for reference in character.get("references") or []:
        if reference["id"] == reference_id:
            return reference
    raise NotFound(f"reference {reference_id} not found")


def find_reference_video(character: dict[str, Any], reference_video_id: str) -> dict[str, Any]:
    for rv in character.get("reference_videos") or []:
        if rv["id"] == reference_video_id:
            return rv
    raise NotFound(f"reference video {reference_video_id} not found")


def find_reference_video_anywhere(data: dict[str, Any], reference_video_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    for video in data["videos"]:
        for character in video.get("characters") or []:
            for rv in character.get("reference_videos") or []:
                if rv["id"] == reference_video_id:
                    return video, character, rv
    raise NotFound(f"reference video {reference_video_id} not found")


def find_character_anywhere(data: dict[str, Any], character_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for video in data["videos"]:
        for character in video.get("characters") or []:
            if character["id"] == character_id:
                return video, character
    raise NotFound(f"character {character_id} not found")


def update_clip(video_id: str, clip_id: str, **fields: Any) -> None:
    def apply(data: dict[str, Any]) -> None:
        video = find_video(data, video_id)
        clip = find_clip(video, clip_id)
        clip.update(fields)

    mutate(apply)


def update_character(video_id: str, character_id: str, **fields: Any) -> None:
    def apply(data: dict[str, Any]) -> None:
        video = find_video(data, video_id)
        character = find_character(video, character_id)
        character.update(fields)

    mutate(apply)


def update_reference_video(video_id: str, character_id: str, reference_video_id: str, **fields: Any) -> None:
    def apply(data: dict[str, Any]) -> None:
        video = find_video(data, video_id)
        character = find_character(video, character_id)
        rv = find_reference_video(character, reference_video_id)
        rv.update(fields)

    mutate(apply)


def update_reference_video_upscale(video_id: str, character_id: str, reference_video_id: str, **fields: Any) -> None:
    def apply(data: dict[str, Any]) -> None:
        video = find_video(data, video_id)
        character = find_character(video, character_id)
        rv = find_reference_video(character, reference_video_id)
        rv.setdefault("upscale", {}).update(fields)

    mutate(apply)


def update_reference_upscale(video_id: str, character_id: str, reference_id: str, **fields: Any) -> None:
    def apply(data: dict[str, Any]) -> None:
        video = find_video(data, video_id)
        character = find_character(video, character_id)
        reference = find_reference(character, reference_id)
        reference.setdefault("upscale", {}).update(fields)

    mutate(apply)


# ---------------------------------------------------------- prompt tags --
# Global (not per-video), reusable named prompt snippets — e.g. a "neutral
# spanish" tag holding the accent/register wording repeated across many
# clips/characters' dialogue instructions, so it's editable in one place
# instead of retyped verbatim everywhere. Referenced inline in any free-text
# prompt field as `[[key]]`; see prompt.py::expand_prompt_tags for the
# substitution step that runs right before a generation is submitted.

def load_prompt_tags() -> list[dict[str, Any]]:
    with _LOCK:
        if not PROMPT_TAGS_PATH.exists():
            return []
        try:
            return json.loads(PROMPT_TAGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []


def save_prompt_tags(tags: list[dict[str, Any]]) -> None:
    with _LOCK:
        PROMPT_TAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROMPT_TAGS_PATH.write_text(json.dumps(tags, indent=2, ensure_ascii=False), encoding="utf-8")


def create_prompt_tag(name: str, key: str, body: str) -> dict[str, Any]:
    with _LOCK:
        tags = load_prompt_tags()
        if any(t["key"] == key for t in tags):
            raise ValueError(f"prompt tag key '{key}' already exists")
        tag = {"id": new_id(), "name": name, "key": key, "body": body}
        tags.append(tag)
        save_prompt_tags(tags)
        return tag


def update_prompt_tag(tag_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        tags = load_prompt_tags()
        tag = next((t for t in tags if t["id"] == tag_id), None)
        if tag is None:
            raise NotFound(f"prompt tag {tag_id} not found")
        new_key = fields.get("key")
        if new_key and new_key != tag["key"] and any(t["key"] == new_key for t in tags if t["id"] != tag_id):
            raise ValueError(f"prompt tag key '{new_key}' already exists")
        tag.update(fields)
        save_prompt_tags(tags)
        return tag


def delete_prompt_tag(tag_id: str) -> None:
    with _LOCK:
        tags = load_prompt_tags()
        remaining = [t for t in tags if t["id"] != tag_id]
        if len(remaining) == len(tags):
            raise NotFound(f"prompt tag {tag_id} not found")
        save_prompt_tags(remaining)


# ------------------------------------------------------------ animate jobs --
# Standalone Wan2.2-Animate "Replacement mode" jobs — a flat list, NOT part
# of the H3 Video/Clip chain concept. See backend/animate.py for settings
# composition (the Animate equivalent of prompt.py).

def load_animate_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        if not ANIMATE_JOBS_PATH.exists():
            return []
        try:
            return json.loads(ANIMATE_JOBS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []


def save_animate_jobs(jobs: list[dict[str, Any]]) -> None:
    with _LOCK:
        ANIMATE_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ANIMATE_JOBS_PATH.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")


def create_animate_job(**fields: Any) -> dict[str, Any]:
    with _LOCK:
        jobs = load_animate_jobs()
        job = {
            "id": new_id(),
            "created_at": time.time(),
            "label": "",
            "control_video_path": "",
            "character_image_path": "",
            "mask_path": None,
            "prompt": "",
            "mode": "replace",
            "relighting": False,
            "seed": -1,
            "video_length": 81,
            "resolution": "832x480",
            "status": "draft",
            "job_id": None,
            "output_path": None,
            "error": None,
            "generation_duration_seconds": None,
            **fields,
        }
        jobs.append(job)
        save_animate_jobs(jobs)
        return job


def find_animate_job(animate_job_id: str) -> dict[str, Any]:
    for job in load_animate_jobs():
        if job["id"] == animate_job_id:
            return job
    raise NotFound(f"animate job {animate_job_id} not found")


def update_animate_job(animate_job_id: str, **fields: Any) -> dict[str, Any]:
    # animate_job_id (this record's own "id") is intentionally not named
    # job_id: callers also set a "job_id" *field* (the underlying WanGP
    # JobStore task id, mirroring clip's own job_id field) via **fields, and
    # a same-named positional parameter would collide with that keyword arg.
    with _LOCK:
        jobs = load_animate_jobs()
        job = next((j for j in jobs if j["id"] == animate_job_id), None)
        if job is None:
            raise NotFound(f"animate job {animate_job_id} not found")
        job.update(fields)
        save_animate_jobs(jobs)
        return job


def delete_animate_job(animate_job_id: str) -> None:
    with _LOCK:
        jobs = load_animate_jobs()
        remaining = [j for j in jobs if j["id"] != animate_job_id]
        if len(remaining) == len(jobs):
            raise NotFound(f"animate job {animate_job_id} not found")
        save_animate_jobs(remaining)


def migrate_reference_video_shape() -> None:
    """One-time migration: characters used to carry a single `reference_video`
    dict + a `reference_video_upscale` dict + a `use_reference_video` bool.
    That's now `reference_videos` (a list, the reference-video "studio") +
    `active_reference_video_id`. Folds any old-shape data into the new shape
    on startup, in place, so existing generated reference videos aren't lost.
    Also renames each entry's old single `prompt` field to `action_prompt`
    (the studio's `prompt` field was later split into `character_prompt` +
    `action_prompt`) — safe to re-run, only touches entries still carrying
    the old key."""

    def apply(data: dict[str, Any]) -> None:
        for video in data["videos"]:
            for character in video.get("characters") or []:
                old_rv = character.pop("reference_video", None)
                old_upscale = character.pop("reference_video_upscale", None)
                had_active = character.pop("use_reference_video", False)
                character.setdefault("reference_videos", [])
                character.setdefault("active_reference_video_id", None)
                if old_rv and (old_rv.get("prompt") or old_rv.get("output_path") or old_rv.get("status", "none") != "none"):
                    new_id_str = uuid.uuid4().hex
                    entry = {
                        "id": new_id_str,
                        "name": "Reference video",
                        "environment_prompt": "",
                        "character_prompt": "",
                        "action_prompt": old_rv.get("prompt", ""),
                        "seed": old_rv.get("seed", -1),
                        "video_length": old_rv.get("video_length", 174),
                        "status": old_rv.get("status", "none"),
                        "job_id": old_rv.get("job_id"),
                        "output_path": old_rv.get("output_path"),
                        "error": old_rv.get("error"),
                        "upscale": {
                            "status": (old_upscale or {}).get("status", "none"),
                            "job_id": (old_upscale or {}).get("job_id"),
                            "output_path": (old_upscale or {}).get("output_path"),
                            "error": (old_upscale or {}).get("error"),
                        },
                    }
                    character["reference_videos"].append(entry)
                    if had_active:
                        character["active_reference_video_id"] = new_id_str

                for rv in character.get("reference_videos") or []:
                    if "prompt" in rv:
                        old_prompt = rv.pop("prompt")
                        rv.setdefault("action_prompt", old_prompt)
                    rv.setdefault("environment_prompt", "")
                    rv.setdefault("character_prompt", "")
                    if not rv.get("style_prompt"):
                        # CINEMATIC_REALISM_PRESET was hardcoded before style_prompt
                        # existed as its own field — backfill it so behavior doesn't
                        # silently change for entries created before this field did.
                        from . import prompt as _prompt

                        rv["style_prompt"] = _prompt.CINEMATIC_REALISM_PRESET

    mutate(apply)
