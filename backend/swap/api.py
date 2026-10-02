"""HTTP routes of the Swap feature. Mounted by backend/main.py; the job store is injected at startup."""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import cv2
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from . import assemble, graph, prompts, runner, scenes, store, upscale, viggle

router = APIRouter()

_job_store: Any = None
_release_wangp: Callable[[], None] = lambda: None
_client_factory: Callable[[], Any] = runner.ComfyClient
ACTIVE = ("queued", "running")


def set_job_store(js: Any, release_wangp: Callable[[], None] | None = None, client_factory: Callable[[], Any] | None = None) -> None:
    global _job_store, _release_wangp, _client_factory
    _job_store = js
    if release_wangp is not None:
        _release_wangp = release_wangp
    if client_factory is not None:
        _client_factory = client_factory


def _characters_provider() -> list[dict[str, Any]]:
    from .. import store as main_store
    out: list[dict[str, Any]] = []
    for video in main_store.load()["videos"]:
        for ch in video.get("characters") or []:
            refs = ch.get("references") or []
            if ch.get("kind", "person") != "person" or not refs:
                continue
            out.append({"video_id": video["id"], "video_title": video.get("title") or "", "character_id": ch["id"],
                        "name": ch.get("name") or "", "image_path": refs[0]["path"],
                        "appearance": prompts.clean_look(ch.get("identity_description") or ""), "outfit": ch.get("wardrobe_notes") or ""})
    return out


# ------------------------------------------------------------------ views --

def media_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    try:
        rel = Path(path_str).resolve().relative_to(store.ROOT.resolve())
    except ValueError:
        return None
    return f"/swap-media/{rel.as_posix()}"


def _raw_frames(p: dict[str, Any], chunk: dict[str, Any]) -> int | None:
    """Frames of the full render behind this pass's result (a result made before this was recorded: read from the file)."""
    if p.get("raw_frames"):
        return p["raw_frames"]
    if p.get("raw_path") and Path(p["raw_path"]).exists():
        cap = cv2.VideoCapture(str(p["raw_path"]))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        return n or None
    return chunk.get("padded_frames")


def _pass_params(project: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """What this pass is (or was) rendered with, for display while it is queued or running."""
    viggle_run = p.get("method") == "viggle"
    q = {"steps": 3, "sampler": "euler", "lora": None} if viggle_run else graph.QUALITY.get(p.get("quality"), graph.QUALITY["final"])
    scene = next((s for s in project["scenes"] if s["index"] == p["scene_index"]), {})
    chunk = next((c for c in scene.get("chunks", []) if c["index"] == p["chunk_index"]), {})
    person = next((x for x in scene.get("people", []) if x["id"] == p["person_id"]), {})
    cast = next((c for c in project["cast"] if c["id"] == person.get("cast_id")), {})
    loras = (["Viggle-Animate (3-step distilled)"] if viggle_run
             else [f"{n} ({st})" for n, st in graph.lora_chain(p.get("quality") or "final", [tuple(x) for x in p.get("extra_loras") or []])])
    return {
        "character": cast.get("name", ""), "target": person.get("target_description", ""),
        "steps": q["steps"], "sampler": q["sampler"], "scheduler": "simple", "turbo": bool(q["lora"]), "quality": p.get("quality") or "final",
        "loras": loras,
        "model": "viggle_animate" if viggle_run else graph.UNET, "width": p.get("width") or project["settings"]["width"], "height": p.get("height") or project["settings"]["height"],
        "seed": p.get("seed") or project["settings"]["seed"], "frames_24": chunk.get("frames_24"), "padded_frames": chunk.get("padded_frames"),
        "method": p.get("method") or "lora", "raw_frames": _raw_frames(p, chunk), "lead_frames": p.get("lead_frames") or 0, "lead_used": p.get("lead_used") or 0, "trim_frames": p.get("trim_frames") or chunk.get("frames_24"),
        "source": "original footage" if p["order"] == 0 else f"output of the previous pass (person {p['order']}) of this chunk",
    }


def _scene_clip(project: dict[str, Any], scene: dict[str, Any]) -> Path:
    return store.project_dir(project) / "thumbs" / f"clip_{scene['start_frame_src']}_{scene['end_frame_src']}.mp4"


def ensure_scene_clips(project: dict[str, Any]) -> None:
    """Cuts every scene of the original into its own 24 fps clip (the UI plays these beside the swapped results; a stretch
    of one long file did not loop reliably). Existing clips are kept."""
    for scene in project["scenes"]:
        dest = _scene_clip(project, scene)
        if dest.exists() or not Path(project["source"]["path"]).exists():
            continue
        try:
            scenes.extract_segment(project["source"]["path"], str(dest), scene["start_frame_src"], scene["end_frame_src"],
                                   float(project["source"]["fps"]), 0, scene["frames_24"] - 1, None)
        except Exception:  # noqa: BLE001 - the page falls back to no original beside the result
            dest.unlink(missing_ok=True)


def _source_clip_of(p: dict[str, Any], run: dict[str, Any]) -> str | None:
    """The control clip a run was rendered from (the scene plus the footage that follows it), if it is still on disk."""
    out = str(run.get("output_path") or "")
    candidates = [out.replace("_viggle.mp4", "_viggle_clip.mp4")] if run.get("method") == "viggle" else []
    if run.get("raw_path"):
        candidates.append(str(Path(run["raw_path"]).parent / f"{p['id']}_src.mp4"))
    return next((c for c in candidates if c and c != out and Path(c).exists()), None)


def _history_view(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Every run of this pass, oldest first, with media urls; the one in use is flagged. A pass finished before
    history existed gets one synthetic entry for its current result."""
    runs = [dict(h) for h in (p.get("history") or [])]
    if not runs:
        legacy = store.legacy_entry(p)
        runs = [legacy] if legacy else []
    for h in runs:
        h["output_url"] = media_url(h.get("output_path"))
        h["edited_frame_url"] = media_url(h.get("edited_frame"))
        h["raw_url"] = media_url(h.get("raw_path"))
        h["source_clip_url"] = media_url(_source_clip_of(p, h))
        h["active"] = bool(p.get("output_path")) and h.get("output_path") == p.get("output_path")
    return runs


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def project_view(project: dict[str, Any]) -> dict[str, Any]:
    v = copy.deepcopy(project)
    base = store.project_dir(project)
    v["source_url"] = media_url(project["source"].get("path"))
    for s in v["scenes"]:
        thumb = base / "thumbs" / f"f{s['start_frame_src']}.jpg"
        s["thumb_url"] = media_url(str(thumb)) if thumb.exists() else None
        clip = _scene_clip(project, s)
        s["clip_url"] = media_url(str(clip)) if clip.exists() else None
    for p in v["passes"]:
        p["output_url"] = media_url(p.get("output_path"))
        p["raw_url"] = media_url(p.get("raw_path"))
        p["params"] = _pass_params(v, p)
        p["history"] = _history_view(p)
    v["final_url"] = media_url((v.get("final") or {}).get("path"))
    v["size_bytes"] = _dir_size(base)
    return v


def _get(project_id: str) -> dict[str, Any]:
    try:
        return store.find(project_id)
    except store.NotFound:
        raise HTTPException(404, "swap project not found")


def _mutate(project_id: str, fn: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    try:
        return store.update(project_id, fn)
    except store.NotFound:
        raise HTTPException(404, "swap project not found")


# ----------------------------------------------------------------- routes --

@router.get("/swap-characters")
def list_swap_characters():
    return _characters_provider()


@router.get("/swaps")
def list_swaps():
    return [project_view(p) for p in store.load_all()]


@router.post("/swaps")
def create_swap(title: str = Form(""), file: UploadFile = File(...)):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or "source.mp4") or "source.mp4"
    project = store.new_project(title or Path(name).stem, {"path": ""})
    dest = store.project_dir(project) / "source" / name
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        info = scenes.detect_cuts(str(dest))
    except Exception as exc:  # noqa: BLE001
        store.delete(project["id"])
        raise HTTPException(400, f"could not read that video: {exc}")
    if info["frames"] < 5:
        store.delete(project["id"])
        raise HTTPException(400, "that video has fewer than 5 frames")
    w, h = store.default_size(info["width"], info["height"])

    def apply(p: dict[str, Any]) -> None:
        p["source"] = {"path": str(dest), "width": info["width"], "height": info["height"], "fps": info["fps"],
                       "frames": info["frames"], "duration": round(info["frames"] / info["fps"], 2), "has_audio": info["has_audio"]}
        p["settings"]["width"], p["settings"]["height"] = w, h

    return project_view(_mutate(project["id"], apply))


@router.get("/swaps/{project_id}")
def get_swap(project_id: str):
    project = _get(project_id)
    if any(not _scene_clip(project, sc).exists() for sc in project["scenes"]):
        ensure_scene_clips(project)  # first open of a project made before scene clips existed
    return project_view(project)


@router.delete("/swaps/{project_id}")
def delete_swap(project_id: str):
    try:
        store.delete(project_id)
    except store.NotFound:
        raise HTTPException(404, "swap project not found")
    return {"ok": True}


def _write_thumbs(project: dict[str, Any]) -> None:
    thumbs = store.project_dir(project) / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(project["source"]["path"])
    try:
        for s in project["scenes"]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, s["start_frame_src"])
            ok, frame = cap.read()
            if ok:
                h, w = frame.shape[:2]
                frame = cv2.resize(frame, (240, max(2, round(240 * h / w))))
                cv2.imwrite(str(thumbs / f"f{s['start_frame_src']}.jpg"), frame)
    finally:
        cap.release()


@router.post("/swaps/{project_id}/detect-scenes")
def detect_scenes(project_id: str):
    project = _get(project_id)
    if any(p["status"] in ACTIVE for p in project["passes"]):
        raise HTTPException(409, "passes are queued or running; wait or cancel them first")
    info = scenes.detect_cuts(project["source"]["path"])
    s = project["settings"]
    max_chunk = s["chunk_max_preview"] if s["quality"] == "preview" else s["chunk_max_final"]
    built = scenes.build_scenes(info["cuts"], info["frames"], info["fps"], max_chunk)

    def apply(p: dict[str, Any]) -> None:
        store.set_scenes(p, built)

    updated = _mutate(project_id, apply)
    _write_thumbs(updated)
    ensure_scene_clips(updated)
    return project_view(updated)


class CutsBody(BaseModel):
    cuts: list[int]


@router.put("/swaps/{project_id}/cuts")
def set_cuts(project_id: str, body: CutsBody):
    """Split the source at exactly these frames (each cut is the first frame of a new scene). A scene whose frame range is
    unchanged keeps its people; everything planned or rendered is dropped, as with a fresh detection."""
    project = _get(project_id)
    if any(p["status"] in ACTIVE for p in project["passes"]):
        raise HTTPException(409, "passes are queued or running; wait or cancel them first")
    total = project["source"]["frames"]
    cuts = sorted(set(body.cuts))
    if any(not 0 < c < total for c in cuts):
        raise HTTPException(400, f"cuts must be frames between 1 and {total - 1}")
    s = project["settings"]
    max_chunk = s["chunk_max_preview"] if s["quality"] == "preview" else s["chunk_max_final"]
    built = scenes.build_scenes(cuts, total, project["source"]["fps"], max_chunk)
    kept = {(sc["start_frame_src"], sc["end_frame_src"]): sc for sc in project["scenes"]}
    for sc in built:
        old = kept.get((sc["start_frame_src"], sc["end_frame_src"]))
        if old:
            sc["people"], sc["background_text"] = old.get("people", []), old.get("background_text", "")

    def apply(p: dict[str, Any]) -> None:
        store.set_scenes(p, built)

    updated = _mutate(project_id, apply)
    _write_thumbs(updated)
    ensure_scene_clips(updated)
    return project_view(updated)


@router.get("/swaps/{project_id}/frame/{n}")
def source_frame(project_id: str, n: int):
    """One source frame as a JPEG, for placing cuts with frame precision."""
    project = _get(project_id)
    if not 0 <= n < project["source"]["frames"]:
        raise HTTPException(400, "frame out of range")
    cap = cv2.VideoCapture(project["source"]["path"])
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        raise HTTPException(400, "could not read that frame")
    return Response(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=3600"})


class ConfirmBody(BaseModel):
    confirmed: bool


@router.post("/swaps/{project_id}/scenes/confirm")
def confirm_scenes(project_id: str, body: ConfirmBody):
    """The cuts are final (the cast, scenes and run steps open) or open for editing again."""
    project = _get(project_id)
    if body.confirmed and not project["scenes"]:
        raise HTTPException(400, "split the video into scenes first")
    if not body.confirmed and any(p["status"] in ACTIVE for p in project["passes"]):
        raise HTTPException(409, "passes are queued or running; wait or cancel them first")

    def apply(p: dict[str, Any]) -> None:
        p["scenes_confirmed"] = body.confirmed

    return project_view(_mutate(project_id, apply))


class SceneMergeBody(BaseModel):
    index: int


@router.post("/swaps/{project_id}/scenes/merge")
def merge_scenes(project_id: str, body: SceneMergeBody):
    def apply(p: dict[str, Any]) -> None:
        sc = p["scenes"]
        if not 0 <= body.index < len(sc) - 1:
            raise HTTPException(400, "there is no next scene to merge with")
        a, b = sc[body.index], sc[body.index + 1]
        a["end_frame_src"] = b["end_frame_src"]
        a["frames_24"] = scenes.frames_at_24(a["end_frame_src"] - a["start_frame_src"] + 1, p["source"]["fps"])
        del sc[body.index + 1]
        for i, s in enumerate(sc):
            s["index"] = i
        store.rechunk(p)
        p["passes"] = []
        p["plan_notes"] = []

    merged = _mutate(project_id, apply)
    ensure_scene_clips(merged)
    return project_view(merged)


class PatchBody(BaseModel):
    title: str | None = None
    settings: dict[str, Any] | None = None
    cast: list[dict[str, Any]] | None = None
    scenes: list[dict[str, Any]] | None = None


@router.patch("/swaps/{project_id}")
def patch_swap(project_id: str, body: PatchBody):
    def apply(p: dict[str, Any]) -> None:
        if body.title is not None:
            p["title"] = body.title
        if body.settings:
            for k in ("quality", "width", "height", "seed"):
                if k in body.settings:
                    if k == "quality" and body.settings[k] not in graph.QUALITY:
                        raise HTTPException(400, f"unknown quality {body.settings[k]!r}")
                    p["settings"][k] = body.settings[k]
            if "quality" in body.settings:
                store.rechunk(p)
        if body.cast is not None:
            p["cast"] = [{"id": c.get("id") or store.uuid.uuid4().hex, "name": c.get("name", ""), "image_path": c.get("image_path", ""),
                          "appearance": c.get("appearance", ""), "outfit": c.get("outfit", ""), "body": c.get("body", ""),
                          "source_character_id": c.get("source_character_id")} for c in body.cast]
        for patch in body.scenes or []:
            match = next((s for s in p["scenes"] if s["index"] == patch.get("index")), None)
            if match is None:
                raise HTTPException(400, f"scene {patch.get('index')} does not exist")
            if "background_text" in patch:
                match["background_text"] = patch["background_text"] or ""
            if "people" in patch:
                match["people"] = [{"id": x.get("id") or store.uuid.uuid4().hex, "cast_id": x.get("cast_id"),
                                    "target_description": x.get("target_description", ""), "order": int(x.get("order", i))}
                                   for i, x in enumerate(patch["people"] or [])]

    return project_view(_mutate(project_id, apply))


@router.post("/swaps/{project_id}/plan")
def plan_swap(project_id: str):
    project = _get(project_id)
    if any(p["status"] in ACTIVE for p in project["passes"]):
        raise HTTPException(409, "passes are queued or running; wait or cancel them first")
    planned = store.build_plan(project)
    store.carry_history(project["passes"], planned["passes"])
    return project_view(_mutate(project_id, lambda p: p.update(passes=planned["passes"], plan_notes=planned["plan_notes"])))


class PassPatch(BaseModel):
    prompt: str


@router.patch("/swaps/{project_id}/passes/{pass_id}")
def patch_pass(project_id: str, pass_id: str, body: PassPatch):
    _get(project_id)
    try:
        return project_view(store.update_pass(project_id, pass_id, prompt=body.prompt))
    except store.NotFound:
        raise HTTPException(404, "pass not found")


def _submit(project_id: str, pass_id: str) -> None:
    if _job_store is None:
        raise HTTPException(503, "server still starting up")

    def on_queued(job_id: str) -> None:
        store.update_pass(project_id, pass_id, status="queued", job_id=job_id, error=None)

    def on_running() -> None:
        store.update_pass(project_id, pass_id, status="running")

    def on_done(status: str, output_path: Any = None, error: str | None = None, duration_seconds: float | None = None) -> None:
        try:
            current = next(p for p in store.find(project_id)["passes"] if p["id"] == pass_id)
        except (store.NotFound, StopIteration):
            return
        if status != "done" and current["status"] in ACTIVE:
            if error == "Cancelled by user":
                store.update_pass(project_id, pass_id, status="cancelled", error=None)
            else:
                store.update_pass(project_id, pass_id, status="failed", error=error or "failed")

    def on_cancel() -> None:
        store.update_pass(project_id, pass_id, status="cancelled", error=None)
        client = _client_factory()
        client.interrupt()
        client.free()

    r = runner.make_runner(project_id, pass_id, store_mod=store, client_factory=_client_factory, release_wangp=_release_wangp)
    _job_store.submit_callable(r, store.project_dir(store.find(project_id)) / "passes" / f"{pass_id}.mp4", on_done,
                               on_queued=on_queued, on_running=on_running, on_cancel=on_cancel)


class Overrides(BaseModel):
    size: int | None = None  # shorter side in pixels for these passes only (e.g. 320)
    seed: int | None = None
    lead: int | None = None  # frames of real footage before the scene to start the render on (cut off afterwards)


def _apply_overrides(project_id: str, pass_ids: list[str], o: Overrides | None) -> None:
    if o is None or (o.size is None and o.seed is None and o.lead is None):
        return
    project = _get(project_id)
    fields: dict[str, Any] = {}
    if o.size:
        fields["width"], fields["height"] = store.size_for_short_side(project["source"]["width"], project["source"]["height"], o.size)
    if o.seed is not None:
        fields["seed"] = o.seed
    if o.lead is not None:
        fields["lead_frames"] = max(0, o.lead)
    for pid in pass_ids:
        store.update_pass(project_id, pid, **fields)


class RunBody(Overrides):
    quality: str
    scene_index: int | None = None


@router.post("/swaps/{project_id}/run")
def run_swap(project_id: str, body: RunBody):
    if body.quality not in graph.QUALITY:
        raise HTTPException(400, f"unknown quality {body.quality!r}")
    project = _get(project_id)
    if not project["passes"]:
        raise HTTPException(400, "there is no plan yet; build the plan first")
    full_switch = project["settings"]["quality"] != body.quality and body.scene_index is None
    # Scenes whose passes were planned at another quality (e.g. one scene previewed) are re-planned alone.
    stale_scenes = sorted({p["scene_index"] for p in project["passes"]
                           if (body.scene_index is None or p["scene_index"] == body.scene_index) and p["quality"] != body.quality})
    if body.scene_index is not None and project["settings"]["quality"] != body.quality and body.scene_index not in stale_scenes:
        stale_scenes = [body.scene_index]
    if full_switch or stale_scenes:
        targets = [p for p in project["passes"] if full_switch or p["scene_index"] in stale_scenes]
        if any(p["status"] in ACTIVE for p in targets):
            raise HTTPException(409, "passes are queued or running; wait or cancel them first")

        # Preview chunks are shorter than final ones, so another quality re-chunks and re-plans. Only the scenes that
        # need it are re-planned, so the other scenes keep their results and their quality.
        def switch(p: dict[str, Any]) -> None:
            trial = copy.deepcopy(p)
            trial["settings"]["quality"] = body.quality
            store.rechunk(trial)
            planned = store.build_plan(trial)
            if full_switch:
                p["settings"]["quality"] = body.quality
                p["scenes"] = trial["scenes"]
                store.carry_history(p["passes"], planned["passes"])
                p["passes"], p["plan_notes"] = planned["passes"], planned["plan_notes"]
                return
            for idx in stale_scenes:
                scene = next(s for s in p["scenes"] if s["index"] == idx)
                scene["chunks"] = next(s for s in trial["scenes"] if s["index"] == idx)["chunks"]
                fresh = [x for x in planned["passes"] if x["scene_index"] == idx]
                store.carry_history([x for x in p["passes"] if x["scene_index"] == idx], fresh)
                p["passes"] = [x for x in p["passes"] if x["scene_index"] != idx] + fresh
            p["passes"].sort(key=lambda x: (x["scene_index"], x["chunk_index"], x["order"]))

        project = _mutate(project_id, switch)
    scope = [p for p in project["passes"] if body.scene_index is None or p["scene_index"] == body.scene_index]
    blocked = [p for p in scope if p["status"] == "blocked"]
    if blocked:
        raise HTTPException(400, "blocked passes: " + "; ".join(f"scene {p['scene_index'] + 1}: {p['error']}" for p in blocked))
    todo = [p for p in scope if p["status"] in ("draft", "failed", "cancelled")]
    if not todo:
        raise HTTPException(400, "nothing to run in that scope")
    _apply_overrides(project_id, [p["id"] for p in todo], body)
    for p in todo:
        _submit(project_id, p["id"])
    return project_view(_get(project_id))


@router.post("/swaps/{project_id}/passes/{pass_id}/rerun")
def rerun_pass(project_id: str, pass_id: str, body: Overrides | None = None):
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    chain = [p for p in project["passes"] if p["scene_index"] == target["scene_index"]
             and p["chunk_index"] == target["chunk_index"] and p["order"] >= target["order"]]
    if any(p["status"] in ACTIVE for p in chain):
        raise HTTPException(409, "that pass or a later one is already queued or running")

    def reset(pr: dict[str, Any]) -> None:
        for p in pr["passes"]:
            if p["id"] in {c["id"] for c in chain}:
                store.ensure_history(p)
                p.update(status="draft", job_id=None, output_path=None, raw_path=None, mean_luma=None, error=None, seconds=None)

    _mutate(project_id, reset)
    _apply_overrides(project_id, [p["id"] for p in chain], body)
    for p in sorted(chain, key=lambda x: x["order"]):
        _submit(project_id, p["id"])
    return project_view(_get(project_id))


@router.post("/swaps/{project_id}/passes/{pass_id}/cancel")
def cancel_pass(project_id: str, pass_id: str):
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    if target["status"] == "queued":
        store.update_pass(project_id, pass_id, status="cancelled")
    elif target["status"] == "running":
        client = _client_factory()
        client.interrupt()
        client.free()
        store.update_pass(project_id, pass_id, status="cancelled")
    return project_view(_get(project_id))


@router.post("/swaps/{project_id}/assemble")
def assemble_swap(project_id: str):
    project = _get(project_id)
    base = store.project_dir(project)
    segments: list[list[str]] = []
    missing: list[str] = []
    temps: list[Path] = []
    for scene in project["scenes"]:
        passes = [p for p in project["passes"] if p["scene_index"] == scene["index"]]
        files: list[str] = []
        for chunk in scene["chunks"]:
            mine = [p for p in passes if p["chunk_index"] == chunk["index"]]
            if not mine:
                tmp = base / "final" / f"orig_{scene['index']}_{chunk['index']}.mp4"
                scenes.extract_segment(project["source"]["path"], str(tmp), scene["start_frame_src"], scene["end_frame_src"],
                                       float(project["source"]["fps"]), chunk["start"], chunk["end"], None)
                temps.append(tmp)
                files.append(str(tmp))
                continue
            last = max(mine, key=lambda p: p["order"])
            if last["status"] != "done" or not last.get("output_path") or not Path(last["output_path"]).exists():
                missing.append(f"Scene {scene['index'] + 1} chunk {chunk['index'] + 1}")
            else:
                files.append(last["output_path"])
        segments.append(files)
    if missing:
        for t in temps:
            t.unlink(missing_ok=True)
        raise HTTPException(400, "not finished yet: " + ", ".join(missing))
    dest = base / "final" / f"{store._slug(project['title'])}.mp4"
    try:
        assemble.assemble_project(segments, project["source"]["path"], str(dest))
    except Exception as exc:  # noqa: BLE001
        _mutate(project_id, lambda p: p.update(final={"path": None, "status": "failed", "error": str(exc)}))
        raise HTTPException(500, f"assembly failed: {exc}")
    finally:
        for t in temps:
            t.unlink(missing_ok=True)
    return project_view(_mutate(project_id, lambda p: p.update(final={"path": str(dest), "status": "done", "error": None})))


class UseRunBody(BaseModel):
    run_id: str


@router.post("/swaps/{project_id}/passes/{pass_id}/use-run")
def use_run(project_id: str, pass_id: str, body: UseRunBody):
    """Makes an earlier run the pass's active result (the one the final video uses)."""
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    run = next((h for h in (target.get("history") or []) if h["id"] == body.run_id), None)
    if run is None:
        raise HTTPException(404, "run not found")
    if any(p["status"] in ACTIVE for p in project["passes"] if p["scene_index"] == target["scene_index"]):
        raise HTTPException(409, "this scene has passes queued or running; wait or cancel them first")

    def apply(pr: dict[str, Any]) -> None:
        for p in pr["passes"]:
            if p["id"] == pass_id:
                p.update(status="done", error=None, output_path=run["output_path"], raw_path=run["raw_path"], mean_luma=run.get("mean_luma"),
                         lead_used=run.get("lead_used") or 0, raw_frames=run.get("raw_frames"), trim_frames=None,
                         seconds=run.get("seconds"), quality=run["quality"], width=run.get("width"), height=run.get("height"), seed=run.get("seed"))
            elif (p["scene_index"], p["chunk_index"]) == (target["scene_index"], target["chunk_index"]) and p["order"] > target["order"]:
                # a later pass was rendered on top of the previous active result; it has to be run again on this one
                p.update(status="draft", job_id=None, output_path=None, raw_path=None, mean_luma=None, error=None, seconds=None)

    return project_view(_mutate(project_id, apply))


@router.delete("/swaps/{project_id}/passes/{pass_id}/runs/{run_id}")
def delete_run(project_id: str, pass_id: str, run_id: str):
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    run = next((h for h in ((target or {}).get("history") or []) if h["id"] == run_id), None)
    if target is None or run is None:
        raise HTTPException(404, "run not found")
    if run["output_path"] == target.get("output_path"):
        raise HTTPException(409, "that run is the one in use; pick another run first")

    def apply(pr: dict[str, Any]) -> None:
        for p in pr["passes"]:
            if p["id"] == pass_id:
                p["history"] = [h for h in p["history"] if h["id"] != run_id]

    out = project_view(_mutate(project_id, apply))
    for key in ("output_path", "raw_path"):
        try:
            Path(run[key]).unlink(missing_ok=True)
        except (OSError, TypeError, KeyError):
            pass
    return out


class TrimBody(BaseModel):
    frames: int


@router.post("/swaps/{project_id}/passes/{pass_id}/trim")
def trim_pass(project_id: str, pass_id: str, body: TrimBody):
    """Re-cuts the active result to its first N frames, always from the full render, so the cut can grow back."""
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    if target["status"] != "done" or not target.get("raw_path") or not Path(target["raw_path"]).exists():
        raise HTTPException(409, "this pass has no finished render to trim")
    cap = cv2.VideoCapture(str(target["raw_path"]))
    lead = int(target.get("lead_used") or 0)
    total = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) - lead)  # frames available from the scene's start
    cap.release()
    if not 1 <= body.frames <= max(1, total):
        raise HTTPException(400, f"keep between 1 and {total} frames")
    tmp = Path(str(target["output_path"]) + ".trim.mp4")
    try:
        scenes.cut_frames(str(target["raw_path"]), str(tmp), lead, body.frames)
    except RuntimeError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"trimming failed: {exc}")
    tmp.replace(target["output_path"])
    store.update_pass(project_id, pass_id, trim_frames=body.frames, raw_frames=total)
    return project_view(_get(project_id))


class ViggleBody(BaseModel):
    size: int = 640
    seed: int | None = None
    frame_path: str | None = None  # an edited frame made elsewhere; empty = Qwen edits the scene's first frame
    expression: str = ""  # what the face is doing in that frame (mouth open, gaze), told to the edit first
    clip_path: str | None = None  # a 124-frame control clip made elsewhere (e.g. several scenes joined)
    slice_start: int = 0  # where this scene starts inside that clip
    sample_step: float | None = None  # the clip is a slowed-down scene: sample the render every this many frames


@router.post("/swaps/{project_id}/passes/{pass_id}/viggle")
def viggle_pass(project_id: str, pass_id: str, body: ViggleBody):
    """Re-render a pass with Viggle-Animate: identity from one edited frame of the scene instead of a reference portrait."""
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    if target["order"] != 0:
        raise HTTPException(400, "Viggle is only available for the first pass of a scene")
    if any(p["status"] in ACTIVE for p in project["passes"] if p["scene_index"] == target["scene_index"]):
        raise HTTPException(409, "this scene has passes queued or running; wait or cancel them first")
    if _job_store is None:
        raise HTTPException(503, "server still starting up")
    store.update(project_id, lambda pr: [store.ensure_history(x) for x in pr["passes"] if x["id"] == pass_id])
    viggle.start(project_id, pass_id, store_mod=store, job_store=_job_store, release_wangp=_release_wangp, size=body.size, seed=body.seed,
                 frame_path=body.frame_path, expression=body.expression, clip_path=body.clip_path, slice_start=body.slice_start, sample_step=body.sample_step)
    return project_view(_get(project_id))


@router.get("/swap-upscalers")
def swap_upscalers():
    """WanGP's spatial/temporal post-processors for video (FlashVSR, the H3 face refiner, ...), as WanGP reports them."""
    from postprocessing import catalog  # WanGP's own module; importable once the backend has initialised the session
    return catalog.call_processes(catalog.query_processes("video"))


class UpscaleBody(BaseModel):
    process_id: str = "flashvsr"
    multiplier: float = 2.0


@router.post("/swaps/{project_id}/passes/{pass_id}/upscale")
def upscale_pass(project_id: str, pass_id: str, body: UpscaleBody):
    """Upscale/refine the result in use with a WanGP post-processor; the new clip is added to the history, not put in use."""
    project = _get(project_id)
    target = next((p for p in project["passes"] if p["id"] == pass_id), None)
    if target is None:
        raise HTTPException(404, "pass not found")
    if target["status"] != "done" or not target.get("output_path"):
        raise HTTPException(409, "this pass has no finished result to upscale")
    if _job_store is None:
        raise HTTPException(503, "server still starting up")
    store.update(project_id, lambda pr: [store.ensure_history(x) for x in pr["passes"] if x["id"] == pass_id])
    upscale.start(project_id, pass_id, store_mod=store, job_store=_job_store, process_id=body.process_id, multiplier=body.multiplier)
    return project_view(_get(project_id))
