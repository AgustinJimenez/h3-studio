"""FastAPI backend for the clip-based H3 video editor (h3-studio).

This app is not standalone: it runs INSIDE WanGP's own .venv and imports
WanGP's shared.api module directly as source (not an installed package).
It needs a WanGP checkout on disk -- override its location via the
WANGP_ROOT env var if it isn't at the default path below.

Run from this repo's root with WanGP's own venv:
    E:\\repo\\wan2.1gp\\.venv\\Scripts\\python.exe -m uvicorn backend.main:app --reload --port 8787
"""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# h3-studio and WanGP are sibling checkouts on disk, not nested -- this is a
# runtime dependency on WanGP's source tree + its .venv, not something git
# submodules can express (see AGENTS.md's move-to-h3-studio note).
WANGP_ROOT = Path(os.environ.get("WANGP_ROOT", r"E:\repo\wan2.1gp"))
if str(WANGP_ROOT) not in sys.path:
    sys.path.insert(0, str(WANGP_ROOT))

# WanGP always writes a fresh generation into this flat, session-wide
# staging dir first (shared.api.init's output_dir can't vary per task); the
# job watcher then moves the finished file into the owning video's own
# clips/ folder under store.VIDEOS_ROOT. Treat this as transient scratch
# space, not the source of truth for any clip's output.
STAGING_DIR = Path(__file__).resolve().parent / "outputs"
STAGING_DIR.mkdir(parents=True, exist_ok=True)

from . import animate, jobs, options, prompt, qa, store  # noqa: E402

MEDIA_ROOT = store.VIDEOS_ROOT

app = FastAPI(title="H3 Clip Video Editor")

app.add_middleware(
    CORSMiddleware,
    # Matches this app's own frontend dev server on any host (localhost, a
    # LAN IP like 192.168.x.x, ...) so opening the app from another device
    # on the network -- e.g. a Mac reaching http://<this-pc-ip>:5173 -- isn't
    # blocked by CORS. Still scoped to port 5173 specifically, not "*".
    allow_origin_regex=r"http://.*:5173$",
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

store.ANIMATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/animate-media", StaticFiles(directory=str(store.ANIMATE_OUTPUT_DIR)), name="animate-media")

_session = None
_job_store: jobs.JobStore | None = None


@app.on_event("startup")
def _startup() -> None:
    global _session, _job_store
    from shared.api import init

    store.migrate_reference_video_shape()
    _session = init(root=WANGP_ROOT, output_dir=STAGING_DIR, console_output=True)
    _job_store = jobs.JobStore(_session)


@app.on_event("shutdown")
def _shutdown() -> None:
    if _session is not None:
        _session.close()


# ---------------------------------------------------------------- helpers --

def _prompt_tags_by_key() -> dict[str, str]:
    return {t["key"]: t["body"] for t in store.load_prompt_tags()}


def to_output_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    try:
        rel = Path(path_str).resolve().relative_to(MEDIA_ROOT.resolve())
    except ValueError:
        return None
    return f"/media/{rel.as_posix()}"


def animate_output_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    try:
        rel = Path(path_str).resolve().relative_to(store.ANIMATE_OUTPUT_DIR.resolve())
    except ValueError:
        return None
    return f"/animate-media/{rel.as_posix()}"


def animate_job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {**job, "output_url": animate_output_url(job.get("output_path"))}


def clip_view(clip: dict[str, Any]) -> dict[str, Any]:
    # own_segment_url: this clip's own new portion only (trimmed of the
    # inherited lead-in from continuation mode), for review — falls back to
    # the full output when there's nothing to trim (not a continuation clip).
    own_segment_url = to_output_url(clip.get("own_segment_path")) or to_output_url(clip.get("output_path"))
    tail_frame_urls = [url for p in (clip.get("tail_frame_paths") or []) if (url := to_output_url(p))]
    upscale = clip.get("upscale") or {}
    return {
        **clip,
        "output_url": to_output_url(clip.get("output_path")),
        "own_segment_url": own_segment_url,
        "tail_frame_urls": tail_frame_urls,
        "upscale": {**upscale, "output_url": to_output_url(upscale.get("output_path"))} if upscale else upscale,
    }


def reference_video_view(rv: dict[str, Any]) -> dict[str, Any]:
    upscale = rv.get("upscale") or {}
    return {
        **rv,
        "output_url": to_output_url(rv.get("output_path")),
        "upscale": {**upscale, "output_url": to_output_url(upscale.get("output_path"))},
    }


def reference_view(ref: dict[str, Any]) -> dict[str, Any]:
    upscale = ref.get("upscale") or {}
    return {
        **ref,
        "upscale": {**upscale, "output_url": to_output_url(upscale.get("output_path"))} if upscale else upscale,
    }


def character_view(character: dict[str, Any]) -> dict[str, Any]:
    return {
        **character,
        "references": [reference_view(r) for r in character.get("references") or []],
        "reference_videos": [reference_video_view(rv) for rv in character.get("reference_videos") or []],
        # Same numbering build_reference_video_settings actually uses (a
        # solo [character] list, not the whole video's roster) -- so the
        # reference-video studio's prompt fields can offer the right
        # <Subject 1>/<Picture N> tags for this character in isolation.
        "model_tags": prompt.compose_model_tags([character]),
    }


def video_view(video: dict[str, Any]) -> dict[str, Any]:
    characters = video.get("characters") or []
    return {
        **video,
        "characters": [character_view(c) for c in sorted(characters, key=lambda c: c["order"])],
        "clips": [clip_view(c) for c in sorted(video["clips"], key=lambda c: c["order"])],
        "concat_output_url": to_output_url(video.get("concat_output_path")),
        # Read-only preview of what generation will actually send — these
        # sections are always derived from `characters`, never hand-edited.
        "composed_subject_definitions": prompt.compose_subject_definitions(characters),
        "composed_retention_analysis": prompt.compose_retention_analysis(characters),
        "model_tags": prompt.compose_model_tags(characters),
    }


def _find_thumbnail_url(video: dict[str, Any]) -> str | None:
    for clip in video.get("clips") or []:
        if clip.get("tail_frame_paths"):
            return to_output_url(clip["tail_frame_paths"][0])
        if clip.get("output_path"):
            return to_output_url(clip["output_path"])
    if video.get("concat_output_path"):
        return to_output_url(video["concat_output_path"])
    return None


def _calculate_total_duration(video: dict[str, Any]) -> float:
    total = 0.0
    done_by_order = {
        c["order"]: c
        for c in video.get("clips", [])
        if c["status"] == "done" and c.get("output_path")
    }
    for order, clip in done_by_order.items():
        next_clip = done_by_order.get(order + 1)
        if next_clip is not None and next_clip.get("continue_from_previous"):
            continue
        frames = clip.get("video_length", 124)
        total += frames / 24.0
    return round(total, 1)


def video_summary(video: dict[str, Any]) -> dict[str, Any]:
    clips = video.get("clips") or []
    characters = video.get("characters") or []
    settings = video.get("template_settings") or {}

    char_names = [c["name"] for c in characters if c.get("name")]
    char_avatars = []
    for c in characters:
        for ref in c.get("references") or []:
            if ref.get("type") == "image" and ref.get("path"):
                char_avatars.append(to_output_url(ref["path"]))
                break

    return {
        "id": video["id"],
        "title": video["title"],
        "created_at": video.get("created_at"),
        "clip_count": len(clips),
        "done_count": sum(1 for c in clips if c["status"] == "done"),
        "thumbnail_url": _find_thumbnail_url(video),
        "concat_output_url": to_output_url(video.get("concat_output_path")),
        "resolution": settings.get("resolution", "1280x704"),
        "model_type": settings.get("model_type", "minimax_h3_ref2va"),
        "character_names": char_names,
        "character_avatars": char_avatars[:4],
        "total_duration_seconds": _calculate_total_duration(video),
        "has_running_job": any(c.get("status") in ("running", "queued") for c in clips),
    }


# -------------------------------------------------------------- pydantic ---

class VideoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    template_settings: Optional[dict[str, Any]] = None
    base_prompt: Optional[dict[str, str]] = None


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    template_settings: Optional[dict[str, Any]] = None
    base_prompt: Optional[dict[str, str]] = None


class ClipCreate(BaseModel):
    shot_prompt: str = ""
    seed: int = -1
    video_length: Optional[int] = None
    continue_from_previous: bool = False
    continuation_keep_frames: Optional[int] = None
    bridge_to_next: bool = False
    active_character_ids: Optional[list[str]] = None


class ClipUpdate(BaseModel):
    shot_prompt: Optional[str] = None
    seed: Optional[int] = None
    video_length: Optional[int] = None
    continue_from_previous: Optional[bool] = None
    continuation_keep_frames: Optional[int] = None
    bridge_to_next: Optional[bool] = None
    active_character_ids: Optional[list[str]] = None


class ReorderRequest(BaseModel):
    clip_ids: list[str]


class CharacterCreate(BaseModel):
    name: str = ""
    identity_description: str = ""
    wardrobe_notes: str = ""
    retention: str = "fully_preserved"


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    identity_description: Optional[str] = None
    wardrobe_notes: Optional[str] = None
    retention: Optional[str] = None
    # id of a reference_videos[] entry to substitute for this character's raw
    # references in future generations, or "" to clear it back to raw refs.
    active_reference_video_id: Optional[str] = None


class ReferenceCreate(BaseModel):
    type: str  # "image" | "video" | "audio"
    path: str
    note: str = ""  # e.g. "wardrobe and costume style reference" — see prompt.py's
    # compose_subject_definitions: a non-empty note keeps this reference OUT of the
    # character's identity clause and calls it out separately instead, so it can't
    # silently leak facial/proportion/art-style traits it wasn't meant to contribute.
    # Experimental (2026-08-19): only meaningful for type="video". When True, the
    # video is fed as H3's "DV" depth-transfer control mode (DepthAnything-extracted
    # geometry only) instead of the default "V-" raw-frame reference mode — see
    # prompt.py::compose_references. Testing whether this avoids the raw-reference
    # mode's appearance/identity leakage from whoever is actually in the source video.
    depth_transfer: bool = False


class ReferenceVideoCreate(BaseModel):
    name: str = ""
    style_prompt: str = ""  # defaults to prompt.CINEMATIC_REALISM_PRESET if left blank
    environment_prompt: str = ""
    character_prompt: str = ""
    action_prompt: str = ""
    seed: int = -1
    video_length: int = 174


class ReferenceVideoUpdate(BaseModel):
    name: Optional[str] = None
    style_prompt: Optional[str] = None
    environment_prompt: Optional[str] = None
    character_prompt: Optional[str] = None
    action_prompt: Optional[str] = None
    seed: Optional[int] = None
    video_length: Optional[int] = None


class CaptureFrameRequest(BaseModel):
    timestamp: float
    source: str = "auto"  # "auto" (prefer upscaled, fall back to raw) | "raw" | "upscaled"
    note: str = ""


class PromptTagCreate(BaseModel):
    name: str
    key: str  # referenced inline in any free-text prompt field as [[key]]
    body: str


class PromptTagUpdate(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    body: Optional[str] = None


# ----------------------------------------------------------------- options -

@app.get("/options")
def get_generation_options(model_type: Optional[str] = None):
    """Real WanGP-sourced dropdown choices (resolution/attention/profile/
    model type) for the frontend's template_settings form — see options.py."""
    if _session is None:
        raise HTTPException(503, "server still starting up")
    return options.get_generation_options(_session, model_type)


# ------------------------------------------------------------- prompt tags -
# Global, reusable named prompt snippets (see store.py's module docstring) —
# expanded from `[[key]]` tokens into their body text right before a
# generation is submitted (prompt.py::expand_prompt_tags, called from
# generate_clip/generate_reference_video below).

_TAG_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@app.get("/prompt-tags")
def list_prompt_tags():
    return store.load_prompt_tags()


@app.post("/prompt-tags")
def create_prompt_tag(body: PromptTagCreate):
    if not _TAG_KEY_RE.match(body.key):
        raise HTTPException(400, "key must contain only letters, numbers, underscores, or hyphens")
    try:
        return store.create_prompt_tag(body.name, body.key, body.body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.put("/prompt-tags/{tag_id}")
def update_prompt_tag(tag_id: str, body: PromptTagUpdate):
    if body.key is not None and not _TAG_KEY_RE.match(body.key):
        raise HTTPException(400, "key must contain only letters, numbers, underscores, or hyphens")
    try:
        return store.update_prompt_tag(tag_id, **body.model_dump(exclude_none=True))
    except store.NotFound:
        raise HTTPException(404, "prompt tag not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/prompt-tags/{tag_id}")
def delete_prompt_tag(tag_id: str):
    try:
        store.delete_prompt_tag(tag_id)
    except store.NotFound:
        raise HTTPException(404, "prompt tag not found")
    return {"ok": True}


# ----------------------------------------------------------- video routes -

@app.get("/videos")
def list_videos():
    data = store.load()
    return [video_summary(v) for v in data["videos"]]


@app.post("/videos")
def create_video(body: VideoCreate):
    video = store.create_video(
        title=body.title,
        description=body.description or "",
        template_settings={**prompt.DEFAULT_TEMPLATE_SETTINGS, **(body.template_settings or {})},
        base_prompt={**prompt.DEFAULT_BASE_PROMPT, **(body.base_prompt or {})},
    )
    return video_view(video)


@app.get("/videos/{video_id}")
def get_video(video_id: str):
    data = store.load()
    try:
        video = store.find_video(data, video_id)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    return video_view(video)


@app.put("/videos/{video_id}")
def update_video(video_id: str, body: VideoUpdate):
    def apply(data):
        video = store.find_video(data, video_id)
        if body.title is not None:
            video["title"] = body.title
        if body.description is not None:
            video["description"] = body.description
        if body.template_settings is not None:
            video["template_settings"] = {**video["template_settings"], **body.template_settings}
        if body.base_prompt is not None:
            video["base_prompt"] = {**video["base_prompt"], **body.base_prompt}
        return video

    try:
        video = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    return video_view(video)


@app.delete("/videos/{video_id}")
def delete_video(video_id: str):
    try:
        store.remove_video(video_id)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    return {"ok": True}


# ------------------------------------------------------- character routes -

@app.get("/videos/{video_id}/characters/{character_id}")
def get_character(video_id: str, character_id: str):
    data = store.load()
    try:
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return character_view(character)


@app.post("/videos/{video_id}/characters")
def create_character(video_id: str, body: CharacterCreate):
    def apply(data):
        video = store.find_video(data, video_id)
        character = {
            **copy.deepcopy(prompt.DEFAULT_CHARACTER),
            "id": store.new_id(),
            "order": len(video.setdefault("characters", [])),
            "name": body.name,
            "identity_description": body.identity_description,
            "wardrobe_notes": body.wardrobe_notes,
            "retention": body.retention,
        }
        video["characters"].append(character)
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    return character_view(character)


@app.put("/videos/{video_id}/characters/{character_id}")
def update_character(video_id: str, character_id: str, body: CharacterUpdate):
    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        if body.name is not None:
            character["name"] = body.name
        if body.identity_description is not None:
            character["identity_description"] = body.identity_description
        if body.wardrobe_notes is not None:
            character["wardrobe_notes"] = body.wardrobe_notes
        if body.retention is not None:
            character["retention"] = body.retention
        if body.active_reference_video_id is not None:
            character["active_reference_video_id"] = body.active_reference_video_id or None
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return character_view(character)


# ------------------------------------------- reference-video "studio" routes -
# A character can hold any number of small generated reference videos (a
# turnaround, a specific pose/emotion, ...) instead of just one — each is
# independently generatable, upscalable, and frame-pickable. See AGENTS.md.

@app.post("/videos/{video_id}/characters/{character_id}/reference-videos")
def create_reference_video(video_id: str, character_id: str, body: ReferenceVideoCreate):
    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        rv = {
            **copy.deepcopy(prompt.DEFAULT_REFERENCE_VIDEO),
            "id": store.new_id(),
            "name": body.name,
            "environment_prompt": body.environment_prompt,
            "character_prompt": body.character_prompt,
            "action_prompt": body.action_prompt,
            "seed": body.seed,
            "video_length": body.video_length,
        }
        if body.style_prompt:
            rv["style_prompt"] = body.style_prompt
        character.setdefault("reference_videos", []).append(rv)
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return character_view(character)


@app.put("/videos/{video_id}/characters/{character_id}/reference-videos/{reference_video_id}")
def update_reference_video(video_id: str, character_id: str, reference_video_id: str, body: ReferenceVideoUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        store.update_reference_video(video_id, character_id, reference_video_id, **fields)
        data = store.load()
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
    except store.NotFound:
        raise HTTPException(404, "video, character, or reference video not found")
    return character_view(character)


@app.delete("/videos/{video_id}/characters/{character_id}/reference-videos/{reference_video_id}")
def delete_reference_video(video_id: str, character_id: str, reference_video_id: str):
    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        before = len(character.get("reference_videos") or [])
        character["reference_videos"] = [rv for rv in (character.get("reference_videos") or []) if rv["id"] != reference_video_id]
        if len(character["reference_videos"]) == before:
            raise store.NotFound(reference_video_id)
        if character.get("active_reference_video_id") == reference_video_id:
            character["active_reference_video_id"] = None

    try:
        store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video, character, or reference video not found")
    return {"ok": True}


@app.post("/characters/{character_id}/reference-videos/{reference_video_id}/generate")
def generate_reference_video(character_id: str, reference_video_id: str):
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    data = store.load()
    try:
        video, character, reference_video = store.find_reference_video_anywhere(data, reference_video_id)
    except store.NotFound:
        raise HTTPException(404, "reference video not found")
    if character["id"] != character_id:
        raise HTTPException(404, "reference video does not belong to this character")

    try:
        settings = prompt.build_reference_video_settings(video, character, reference_video)
        settings["prompt"] = prompt.expand_prompt_tags(settings["prompt"], _prompt_tags_by_key())
    except prompt.TooManyReferences as exc:
        raise HTTPException(400, str(exc))
    except prompt.UnknownPromptTags as exc:
        raise HTTPException(400, str(exc))
    dest_path = store.characters_dir(video["folder"]) / f"{character_id}_{reference_video_id}.mp4"

    def mark_queued(job_id: str) -> None:
        store.update_reference_video(video["id"], character_id, reference_video_id, status="queued", job_id=job_id, error=None, last_generation_settings=settings)

    def mark_running() -> None:
        store.update_reference_video(video["id"], character_id, reference_video_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        store.update_reference_video(video["id"], character_id, reference_video_id, status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)

    job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": job_id, "status": "queued"}


@app.post("/characters/{character_id}/reference-videos/{reference_video_id}/upscale")
def upscale_reference_video(character_id: str, reference_video_id: str):
    """FlashVSR-upscales one reference-video entry (typically 720p) to
    ~1080p, so capture-frame below has a higher-res source to pull still
    frames from. Standalone postprocessing pass, not a fresh H3 generation —
    same JobStore, since submit_task() accepts any settings dict shaped by
    shared.api's build helpers, not just H3 ones."""
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    data = store.load()
    try:
        video, character, reference_video = store.find_reference_video_anywhere(data, reference_video_id)
    except store.NotFound:
        raise HTTPException(404, "reference video not found")
    if character["id"] != character_id:
        raise HTTPException(404, "reference video does not belong to this character")

    src_path = reference_video.get("output_path")
    if not src_path:
        raise HTTPException(400, "reference video has no completed output to upscale")

    output_filename = f"{video['id']}_char_{character_id}_ref_{reference_video_id}_upscaled"
    settings = prompt.build_upscale_settings(src_path, output_filename, scale=1.5)
    dest_path = store.characters_dir(video["folder"]) / f"{character_id}_{reference_video_id}_upscaled.mp4"

    def mark_queued(job_id: str) -> None:
        store.update_reference_video_upscale(video["id"], character_id, reference_video_id, status="queued", job_id=job_id, error=None, last_generation_settings=settings)

    def mark_running() -> None:
        store.update_reference_video_upscale(video["id"], character_id, reference_video_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        store.update_reference_video_upscale(video["id"], character_id, reference_video_id, status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)

    job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": job_id, "status": "queued"}


@app.post("/characters/{character_id}/reference-videos/{reference_video_id}/capture-frame")
def capture_reference_frame(character_id: str, reference_video_id: str, body: CaptureFrameRequest):
    """Extracts a single still frame (via ffmpeg) from a reference-video
    entry at a given timestamp and adds it as a new image reference. The
    point: video/audio references are duration-capped at 15s combined
    across ALL characters in a generation, but image_refs are not — pulling
    clean stills out of an (optionally upscaled) reference video sidesteps
    that cap for identity, since H3 reads faces well from images."""
    data = store.load()
    try:
        video, character, reference_video = store.find_reference_video_anywhere(data, reference_video_id)
    except store.NotFound:
        raise HTTPException(404, "reference video not found")
    if character["id"] != character_id:
        raise HTTPException(404, "reference video does not belong to this character")

    upscale = reference_video.get("upscale") or {}
    upscaled_path = upscale.get("output_path") if upscale.get("status") == "done" else None
    raw_path = reference_video.get("output_path")

    if body.source == "raw":
        src_path = raw_path
    elif body.source == "upscaled":
        src_path = upscaled_path
    else:
        src_path = upscaled_path or raw_path
    if not src_path:
        raise HTTPException(400, "no reference video available to capture a frame from")

    characters_dir = store.characters_dir(video["folder"])
    characters_dir.mkdir(parents=True, exist_ok=True)
    frame_id = store.new_id()
    frame_path = characters_dir / f"{character_id}_frame_{frame_id}.png"

    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(body.timestamp), "-i", str(src_path), "-frames:v", "1", str(frame_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not frame_path.exists():
        raise HTTPException(500, f"ffmpeg frame extraction failed: {result.stderr[-500:]}")

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        v = store.find_video(data, video["id"])
        c = store.find_character(v, character_id)
        reference = {"id": store.new_id(), "type": "image", "path": str(frame_path), "note": body.note}
        c.setdefault("references", []).append(reference)
        return c

    character = store.mutate(apply)
    return character_view(character)


@app.delete("/videos/{video_id}/characters/{character_id}")
def delete_character(video_id: str, character_id: str):
    def apply(data):
        video = store.find_video(data, video_id)
        before = len(video.get("characters") or [])
        video["characters"] = [c for c in (video.get("characters") or []) if c["id"] != character_id]
        if len(video["characters"]) == before:
            raise store.NotFound(character_id)
        for index, character in enumerate(sorted(video["characters"], key=lambda c: c["order"])):
            character["order"] = index

    try:
        store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return {"ok": True}


@app.post("/videos/{video_id}/characters/{character_id}/references")
def add_reference(video_id: str, character_id: str, body: ReferenceCreate):
    if body.type not in ("image", "video", "audio"):
        raise HTTPException(400, "type must be 'image', 'video', or 'audio'")

    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        reference = {"id": store.new_id(), "type": body.type, "path": body.path, "note": body.note, "depth_transfer": body.depth_transfer}
        character.setdefault("references", []).append(reference)
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return character_view(character)


@app.post("/videos/{video_id}/characters/{character_id}/references/upload")
async def upload_reference(
    video_id: str,
    character_id: str,
    ref_type: str = Form(..., alias="type"),
    note: str = Form(""),
    file: UploadFile = File(...),
):
    """Same as POST .../references, but for a file the user picked from their
    own machine rather than an existing path already on this server -- saves
    it under this character's own data folder (same convention as captured
    reference-video frames/upscales) and registers it with that saved path."""
    if ref_type not in ("image", "video", "audio"):
        raise HTTPException(400, "type must be 'image', 'video', or 'audio'")

    data = store.load()
    try:
        video = store.find_video(data, video_id)
    except store.NotFound:
        raise HTTPException(404, "video not found")

    characters_dir = store.characters_dir(video["folder"])
    characters_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "upload")
    dest_path = characters_dir / f"{character_id}_upload_{store.new_id()}_{safe_name}"
    dest_path.write_bytes(await file.read())

    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        reference = {"id": store.new_id(), "type": ref_type, "path": str(dest_path), "note": note, "depth_transfer": False}
        character.setdefault("references", []).append(reference)
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or character not found")
    return character_view(character)


@app.delete("/videos/{video_id}/characters/{character_id}/references/{reference_id}")
def delete_reference(video_id: str, character_id: str, reference_id: str):
    def apply(data):
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        before = len(character.get("references") or [])
        character["references"] = [r for r in (character.get("references") or []) if r["id"] != reference_id]
        if len(character["references"]) == before:
            raise store.NotFound(reference_id)
        return character

    try:
        character = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video, character, or reference not found")
    return character_view(character)


@app.post("/videos/{video_id}/characters/{character_id}/references/{reference_id}/upscale")
def upscale_reference(video_id: str, character_id: str, reference_id: str):
    """FlashVSR-upscales a single picked image reference in place (a
    captured frame, or any other image reference) — same edit_postprocessing
    settings as the video upscale above, wgp.py just auto-detects image vs
    video from the file extension. Never overwrites the original file;
    prompt.py's effective_path() prefers the upscale output once it's done."""
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    data = store.load()
    try:
        video = store.find_video(data, video_id)
        character = store.find_character(video, character_id)
        reference = store.find_reference(character, reference_id)
    except store.NotFound:
        raise HTTPException(404, "video, character, or reference not found")

    if reference.get("type") != "image":
        raise HTTPException(400, "only image references can be upscaled")
    src_path = reference.get("path")
    if not src_path:
        raise HTTPException(400, "reference has no file to upscale")

    output_filename = f"{video_id}_ref_{reference_id}_upscaled"
    settings = prompt.build_upscale_settings(src_path, output_filename, scale=1.5)
    dest_path = store.characters_dir(video["folder"]) / f"{character_id}_ref_{reference_id}_upscaled.png"

    def mark_queued(job_id: str) -> None:
        store.update_reference_upscale(video_id, character_id, reference_id, status="queued", job_id=job_id, error=None, last_generation_settings=settings)

    def mark_running() -> None:
        store.update_reference_upscale(video_id, character_id, reference_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        store.update_reference_upscale(video_id, character_id, reference_id, status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)

    job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": job_id, "status": "queued"}


@app.get("/reference-preview")
def reference_preview(path: str):
    """Serve a local reference file (image/video/audio) back to the
    frontend for inline preview. The backend already reads arbitrary local
    paths directly for generation (WanGP does the same), so this is not a
    new trust boundary — just exposing what's already readable."""
    file_path = Path(path)
    if not file_path.is_file():
        raise HTTPException(404, "file not found")
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(str(file_path), media_type=media_type)


# ------------------------------------------------------- animate job routes -
# Standalone Wan2.2-Animate "Replacement mode" jobs — a flat list, separate
# from the Video/Clip chain concept above. See backend/animate.py.

class AnimateJobCreate(BaseModel):
    label: str = ""
    control_video_path: str = ""
    character_image_path: str = ""
    mask_path: Optional[str] = None
    prompt: str = ""
    mode: str = "replace"  # "replace" | "replace_see_through"
    relighting: bool = False
    seed: int = -1
    video_length: Optional[int] = None
    resolution: Optional[str] = None


class AnimateJobUpdate(BaseModel):
    label: Optional[str] = None
    control_video_path: Optional[str] = None
    character_image_path: Optional[str] = None
    mask_path: Optional[str] = None
    prompt: Optional[str] = None
    mode: Optional[str] = None
    relighting: Optional[bool] = None
    seed: Optional[int] = None
    video_length: Optional[int] = None
    resolution: Optional[str] = None


@app.get("/animate-jobs")
def list_animate_jobs():
    return [animate_job_view(j) for j in store.load_animate_jobs()]


@app.post("/animate-jobs")
def create_animate_job(body: AnimateJobCreate):
    job = store.create_animate_job(**body.model_dump())
    return animate_job_view(job)


@app.get("/animate-jobs/{job_id}")
def get_animate_job(job_id: str):
    try:
        job = store.find_animate_job(job_id)
    except store.NotFound:
        raise HTTPException(404, "animate job not found")
    return animate_job_view(job)


@app.put("/animate-jobs/{job_id}")
def update_animate_job(job_id: str, body: AnimateJobUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        job = store.update_animate_job(job_id, **fields)
    except store.NotFound:
        raise HTTPException(404, "animate job not found")
    return animate_job_view(job)


@app.delete("/animate-jobs/{job_id}")
def delete_animate_job(job_id: str):
    try:
        store.delete_animate_job(job_id)
    except store.NotFound:
        raise HTTPException(404, "animate job not found")
    return {"ok": True}


def _generate_full_frame_mask(control_video_path: str, dest_path: Path) -> str:
    """WanGP hard-requires video_mask for Replacement mode's "A" letter
    (wgp.py: "if 'A' in video_prompt_type ... video_mask is None: return
    err('You must provide a Video Mask')") -- there is no server-side
    full-frame auto-fallback reachable before that check, despite
    forced_guide_mask_inputs (confirmed empirically: generation fails
    outright with mask_path omitted, contradicting the initial research).
    Materializes a plain white video (mask value 1 = "replace this area",
    per shared/utils/utils.py's prepare_video_guide_and_mask default of
    torch.ones_like) matching the control video's own resolution/fps/
    duration, so omitting mask_path still means "full frame", just as a
    real file WanGP will accept instead of an implicit default."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-show_entries", "format=duration", "-of", "json", control_video_path,
        ],
        capture_output=True, text=True,
    )
    try:
        info = json.loads(probe.stdout)
        stream = info["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        num, den = stream["r_frame_rate"].split("/")
        fps = float(num) / float(den) if float(den) else 24.0
        duration = float(info["format"]["duration"])
    except (json.JSONDecodeError, KeyError, IndexError, ValueError, ZeroDivisionError) as exc:
        raise RuntimeError(f"could not read control video properties for mask generation: {exc}") from exc

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=white:s={width}x{height}:r={fps}",
            "-t", str(duration), "-pix_fmt", "yuv420p", str(dest_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not dest_path.exists():
        raise RuntimeError(f"ffmpeg full-frame mask generation failed: {result.stderr[-500:]}")
    return str(dest_path)


@app.post("/animate-jobs/{job_id}/generate")
def generate_animate_job(job_id: str):
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    try:
        job = store.find_animate_job(job_id)
    except store.NotFound:
        raise HTTPException(404, "animate job not found")

    if not job.get("control_video_path") or not Path(job["control_video_path"]).is_file():
        raise HTTPException(400, "control_video_path does not point to an existing file")
    if not job.get("character_image_path") or not Path(job["character_image_path"]).is_file():
        raise HTTPException(400, "character_image_path does not point to an existing file")
    if job.get("mask_path"):
        if not Path(job["mask_path"]).is_file():
            raise HTTPException(400, "mask_path does not point to an existing file")
        effective_job = job
    else:
        mask_dest = store.ANIMATE_OUTPUT_DIR / f"{job_id}_full_mask.mp4"
        try:
            generated_mask_path = _generate_full_frame_mask(job["control_video_path"], mask_dest)
        except RuntimeError as exc:
            raise HTTPException(500, str(exc))
        effective_job = {**job, "mask_path": generated_mask_path}

    settings = animate.build_animate_settings(effective_job)
    try:
        settings["prompt"] = prompt.expand_prompt_tags(settings["prompt"], _prompt_tags_by_key())
    except prompt.UnknownPromptTags as exc:
        raise HTTPException(400, str(exc))

    dest_path = store.ANIMATE_OUTPUT_DIR / f"{job_id}.mp4"

    def mark_queued(new_job_id: str) -> None:
        store.update_animate_job(job_id, status="queued", job_id=new_job_id, error=None)

    def mark_running() -> None:
        store.update_animate_job(job_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        store.update_animate_job(job_id, status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)

    new_job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": new_job_id, "status": "queued"}


# ------------------------------------------------------------ clip routes -

@app.post("/videos/{video_id}/clips")
def create_clip(video_id: str, body: ClipCreate):
    def apply(data):
        video = store.find_video(data, video_id)
        clip = {
            "id": store.new_id(),
            "order": len(video["clips"]),
            "shot_prompt": body.shot_prompt,
            "seed": body.seed,
            "video_length": body.video_length or prompt.DEFAULT_VIDEO_LENGTH,
            "continue_from_previous": body.continue_from_previous,
            "continuation_keep_frames": body.continuation_keep_frames,
            "bridge_to_next": body.bridge_to_next,
            "active_character_ids": body.active_character_ids,
            "status": "draft",
            "job_id": None,
            "output_path": None,
            "error": None,
        }
        video["clips"].append(clip)
        return clip

    try:
        clip = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    return clip_view(clip)


@app.put("/videos/{video_id}/clips/{clip_id}")
def update_clip(video_id: str, clip_id: str, body: ClipUpdate):
    def apply(data):
        video = store.find_video(data, video_id)
        clip = store.find_clip(video, clip_id)
        if body.shot_prompt is not None:
            clip["shot_prompt"] = body.shot_prompt
        if body.seed is not None:
            clip["seed"] = body.seed
        if body.video_length is not None:
            clip["video_length"] = body.video_length
        if body.continue_from_previous is not None:
            clip["continue_from_previous"] = body.continue_from_previous
        if body.continuation_keep_frames is not None:
            clip["continuation_keep_frames"] = body.continuation_keep_frames
        if body.bridge_to_next is not None:
            clip["bridge_to_next"] = body.bridge_to_next
        if "active_character_ids" in body.model_fields_set:
            clip["active_character_ids"] = body.active_character_ids
        return clip

    try:
        clip = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or clip not found")
    return clip_view(clip)


@app.delete("/videos/{video_id}/clips/{clip_id}")
def delete_clip(video_id: str, clip_id: str):
    def apply(data):
        video = store.find_video(data, video_id)
        before = len(video["clips"])
        video["clips"] = [c for c in video["clips"] if c["id"] != clip_id]
        if len(video["clips"]) == before:
            raise store.NotFound(clip_id)
        for index, clip in enumerate(sorted(video["clips"], key=lambda c: c["order"])):
            clip["order"] = index

    try:
        store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video or clip not found")
    return {"ok": True}


@app.patch("/videos/{video_id}/clips/reorder")
def reorder_clips(video_id: str, body: ReorderRequest):
    def apply(data):
        video = store.find_video(data, video_id)
        by_id = {c["id"]: c for c in video["clips"]}
        if set(by_id.keys()) != set(body.clip_ids):
            raise ValueError("clip_ids must match the video's existing clip ids exactly")
        for index, clip_id in enumerate(body.clip_ids):
            by_id[clip_id]["order"] = index
        return video

    try:
        video = store.mutate(apply)
    except store.NotFound:
        raise HTTPException(404, "video not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return video_view(video)


# -------------------------------------------------------------- generate --

@app.post("/clips/{clip_id}/generate")
def generate_clip(clip_id: str):
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    data = store.load()
    try:
        video, clip = store.find_clip_anywhere(data, clip_id)
    except store.NotFound:
        raise HTTPException(404, "clip not found")

    previous_clip = None
    if clip.get("continue_from_previous"):
        previous_clip = next((c for c in video.get("clips") or [] if c["order"] == clip["order"] - 1), None)
        if previous_clip is None or previous_clip.get("status") != "done" or not previous_clip.get("output_path"):
            raise HTTPException(400, "continue_from_previous is set but the preceding clip has no completed output to continue from")

    bridge_end_frame_path = None
    if clip.get("bridge_to_next"):
        next_clip = next((c for c in video.get("clips") or [] if c["order"] == clip["order"] + 1), None)
        if next_clip is None or next_clip.get("status") != "done" or not next_clip.get("output_path"):
            raise HTTPException(400, "bridge_to_next is set but the next clip has no completed output to bridge into")
        bridge_dir = store.clips_dir(video["folder"])
        bridge_dir.mkdir(parents=True, exist_ok=True)
        bridge_frame_path = bridge_dir / f"{clip_id}_bridge_target.png"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(next_clip["output_path"]), "-frames:v", "1", str(bridge_frame_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not bridge_frame_path.exists():
            raise HTTPException(500, f"ffmpeg bridge-target frame extraction failed: {result.stderr[-500:]}")
        bridge_end_frame_path = str(bridge_frame_path)

    try:
        settings = prompt.build_generation_settings(video, clip, previous_clip, bridge_end_frame_path)
        settings["prompt"] = prompt.expand_prompt_tags(settings["prompt"], _prompt_tags_by_key())
    except prompt.TooManyReferences as exc:
        raise HTTPException(400, str(exc))
    except prompt.UnknownPromptTags as exc:
        raise HTTPException(400, str(exc))
    dest_path = store.clips_dir(video["folder"]) / f"{clip_id}.mp4"

    def mark_queued(job_id: str) -> None:
        store.update_clip(video["id"], clip_id, status="queued", job_id=job_id, error=None, last_generation_settings=settings)

    def mark_running() -> None:
        store.update_clip(video["id"], clip_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        fields: dict[str, Any] = dict(status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)
        if status == "done" and output_path:
            fields["own_segment_path"] = _compute_own_segment_path(video, clip, output_path)
            fields["tail_frame_paths"] = _extract_tail_frames(video, clip, output_path)
        else:
            fields["own_segment_path"] = None
            fields["tail_frame_paths"] = []
        store.update_clip(video["id"], clip_id, **fields)
        if status == "done" and output_path:
            try:
                _run_concat(video["id"])
            except Exception:
                pass

    job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": job_id, "status": "queued"}


@app.post("/clips/{clip_id}/upscale")
def upscale_clip(clip_id: str):
    """FlashVSR-upscales one finished story clip in place-ish (never
    overwrites the raw output; a sibling `upscale: {status, output_path,
    ...}` sub-dict is attached, same pattern as reference-video/reference
    upscaling above). Useful when clips in this video aren't being
    concatenated into one final output -- each clip is its own deliverable,
    so each needs its own upscale pass rather than one upscale-after-concat
    step."""
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    data = store.load()
    try:
        video, clip = store.find_clip_anywhere(data, clip_id)
    except store.NotFound:
        raise HTTPException(404, "clip not found")

    src_path = clip.get("output_path")
    if not src_path:
        raise HTTPException(400, "clip has no completed output to upscale")

    output_filename = f"{video['id']}_clip_{clip_id}_upscaled"
    settings = prompt.build_upscale_settings(src_path, output_filename, scale=1.5)
    dest_path = store.clips_dir(video["folder"]) / f"{clip_id}_upscaled.mp4"

    def mark_queued(job_id: str) -> None:
        store.update_clip_upscale(video["id"], clip_id, status="queued", job_id=job_id, error=None, last_generation_settings=settings)

    def mark_running() -> None:
        store.update_clip_upscale(video["id"], clip_id, status="running")

    def on_done(status: str, output_path: str | None, error: str | None, duration_seconds: float | None = None) -> None:
        store.update_clip_upscale(video["id"], clip_id, status=status, output_path=output_path, error=error, generation_duration_seconds=duration_seconds)

    job_id = _job_store.submit(settings, dest_path, on_done, on_queued=mark_queued, on_running=mark_running)

    return {"job_id": job_id, "status": "queued"}


@app.post("/clips/{clip_id}/analyze")
def analyze_clip(clip_id: str):
    """On-demand post-generation QA: VideoChat3 for duplicated/cloned
    subjects and ghosting artifacts, speaker verification for voice-bleed
    (see qa.py's module docstring for the full rationale/scope notes).
    Shares the GPU with generation, so it's guarded by the same busy check
    and releases WanGP's own resident model first -- see qa.run_qa."""
    if _job_store is None:
        raise HTTPException(503, "server still starting up")
    if _job_store.is_busy():
        raise HTTPException(409, "a generation is currently running; try again once it finishes")

    data = store.load()
    try:
        video, clip = store.find_clip_anywhere(data, clip_id)
    except store.NotFound:
        raise HTTPException(404, "clip not found")

    if not clip.get("output_path") or not Path(clip["output_path"]).is_file():
        raise HTTPException(400, "clip has no completed output to analyze")

    settings = clip.get("last_generation_settings") or {}
    reference_audio_paths = [p for p in (settings.get("audio_guide"), settings.get("audio_guide2")) if p]
    scene_prompt = settings.get("prompt")

    try:
        report = qa.run_qa(clip["output_path"], reference_audio_paths, _session.release_model, scene_prompt)
    except Exception as exc:  # pragma: no cover - surfaced to the caller, not silently swallowed
        raise HTTPException(500, f"QA analysis failed: {exc}")

    store.update_clip(video["id"], clip_id, qa_report=report)
    return report


@app.post("/unload-model")
def unload_model():
    """Frees the currently-loaded model's GPU/RAM (see
    shared/api.py::WanGPSession.release_model) without shutting the server
    down -- the next generation just transparently reloads. Guarded the
    same way as /clips/{id}/analyze so it can't race an active generation."""
    if _session is None or _job_store is None:
        raise HTTPException(503, "server still starting up")
    if _job_store.is_busy():
        raise HTTPException(409, "a generation is currently running; try again once it finishes")
    _session.release_model()
    return {"ok": True}


class LoadModelRequest(BaseModel):
    model_type: str


@app.get("/model-status")
def model_status():
    if _session is None:
        raise HTTPException(503, "server still starting up")
    return {"model_type": _session.get_current_model_type()}


@app.post("/load-model")
def load_model(body: LoadModelRequest):
    """Preloads a model into GPU/RAM ahead of the first generation that
    needs it (see shared/api.py::WanGPSession.preload_model). Guarded the
    same way as /unload-model so it can't race an active generation."""
    if _session is None or _job_store is None:
        raise HTTPException(503, "server still starting up")
    if _job_store.is_busy():
        raise HTTPException(409, "a generation is currently running; try again once it finishes")
    _session.preload_model(body.model_type)
    return {"ok": True, "model_type": body.model_type}


def _get_video_duration_seconds(path: str) -> float:
    import cv2
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return (frames / fps) if frames and frames > 0 else 0.0


def _extract_tail_frames(video: dict[str, Any], clip: dict[str, Any], output_path: str) -> list[str]:
    """Stills from the literal last ~2s of the clip's own output file."""
    duration = _get_video_duration_seconds(output_path)
    if duration <= 0:
        return []
    start = max(0.0, duration - 2.0)
    dest_dir = store.clips_dir(video["folder"])
    for stale in dest_dir.glob(f"{clip['id']}_tail_*.jpg"):
        stale.unlink(missing_ok=True)
    pattern = dest_dir / f"{clip['id']}_tail_%02d.jpg"
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-y", "-ss", str(start), "-i", str(output_path), "-vf", "fps=2", str(pattern)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(str(p) for p in dest_dir.glob(f"{clip['id']}_tail_*.jpg"))


def _compute_own_segment_path(video: dict[str, Any], clip: dict[str, Any], output_path: str) -> str | None:
    """A continuation clip's own file spans its whole chain so far (e.g.
    clip 2 continuing clip 1 = 0-30s, not just its own new 15-30s). For review
    purposes this trims off the inherited lead-in, producing a clean slice."""
    if not clip.get("continue_from_previous"):
        return None
    previous_clip = next((c for c in video.get("clips") or [] if c["order"] == clip["order"] - 1), None)
    if not previous_clip or not previous_clip.get("output_path"):
        return None
    start = _get_video_duration_seconds(previous_clip["output_path"])
    if start <= 0:
        return None
    dest = store.clips_dir(video["folder"]) / f"{clip['id']}_own_segment.mp4"
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-y", "-ss", str(start), "-i", str(output_path), "-c", "copy", str(dest)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not dest.exists():
        return None
    return str(dest)


@app.get("/videos/{video_id}/clips/{clip_id}")
def get_clip(video_id: str, clip_id: str):
    data = store.load()
    try:
        video = store.find_video(data, video_id)
        clip = store.find_clip(video, clip_id)
    except store.NotFound:
        raise HTTPException(404, "video or clip not found")
    return clip_view(clip)


# ---------------------------------------------------------------- concat --

def _run_concat(video_id: str) -> dict[str, Any]:
    data = store.load()
    video = store.find_video(data, video_id)

    done_by_order = {
        c["order"]: c
        for c in video["clips"]
        if c["status"] == "done" and c.get("output_path")
    }
    if not done_by_order:
        return {"concat_output_path": None, "concat_output_url": None}

    segment_clips = []
    for order, clip in sorted(done_by_order.items()):
        next_clip = done_by_order.get(order + 1)
        if next_clip is not None and next_clip.get("continue_from_previous"):
            continue
        segment_clips.append(clip)

    if not segment_clips:
        return {"concat_output_path": None, "concat_output_url": None}

    video_folder = store.video_dir(video["folder"])
    out_path = video_folder / "concat.mp4"

    # If there is only one continuous master sequence, copy it directly
    # preserving 100% of WanGP's native frame-by-frame temporal perfection without any splice artifacts.
    if len(segment_clips) == 1:
        import shutil
        shutil.copy2(segment_clips[0]["output_path"], out_path)
    else:
        list_path = video_folder / "concat_list.txt"
        list_path.write_text(
            "\n".join(f"file '{Path(c['output_path']).resolve().as_posix()}'" for c in segment_clips),
            encoding="utf-8",
        )
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr[-2000:]}")

    def apply(data):
        v = store.find_video(data, video_id)
        v["concat_output_path"] = str(out_path)

    store.mutate(apply)
    return {"concat_output_path": str(out_path), "concat_output_url": to_output_url(str(out_path))}


@app.post("/videos/{video_id}/concat")
def concat_video(video_id: str):
    try:
        res = _run_concat(video_id)
        if not res.get("concat_output_path"):
            raise HTTPException(400, "no completed clips to join")
        return res
    except store.NotFound:
        raise HTTPException(404, "video not found")
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
