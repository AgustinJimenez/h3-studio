"""Viggle-Animate pass: replace a character in a scene from ONE edited frame of that scene.

Instead of a separate reference portrait (which H3 tends to paste into the shot when the face fills the frame), the identity
comes from a frame of the scene itself, edited so the new person is in the same pose and framing. Two jobs run back to back:
  1. a callable job: cut the 124-frame control clip, take its first frame and have Qwen image edit swap the person in it;
  2. a WanGP job: the Viggle-Animate model (3 steps) follows the clip and applies the edited frame's look.
WanGP merges these settings with the model's own defaults (defaults/viggle_animate.json)."""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2

from . import runner, scenes, store

VIGGLE_MODEL = "viggle_animate"
WINDOW = 124  # Viggle renders in windows of at most 124 frames
PROMPT_PLACEHOLDER = "Prompt ignored."  # the model uses a fixed prompt, but WanGP refuses an empty one


def build_settings(clip: str, frame: str, width: int, height: int, *, seed: int, output_name: str) -> dict[str, Any]:
    return {"model_type": VIGGLE_MODEL, "video_prompt_type": "IVU", "video_guide": str(clip), "image_refs": [str(frame)],
            "resolution": f"{width}x{height}", "seed": int(seed), "prompt": PROMPT_PLACEHOLDER, "video_length": WINDOW,
            "sliding_window_size": WINDOW, "output_filename": output_name}


def first_frame(clip: str, dest: str) -> None:
    cap = cv2.VideoCapture(str(clip))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"could not read the first frame of {clip}")
    cv2.imencode(".png", frame)[1].tofile(str(dest))


def edit_prompt(target: str, cast: dict[str, Any], expression: str = "", view: str = "front") -> str:
    look = (cast.get("appearance") or "").strip().rstrip(".")
    outfit = (cast.get("outfit") or "").strip().rstrip(".")
    if view == "behind":  # the person faces away: the photo only gives the hair and the clothes, never a face
        return (f"Image 1 is a frame of a video. Replace {target} in image 1 with the person from image 2"
                f"{f' ({look})' if look else ''}, still seen from behind: show the back of their hair and head, and the back of the outfit "
                f"they wear ({outfit}). They face away from the camera exactly like the original person: do not show their face at all. "
                "Keep image 1's exact pose, head angle, camera framing, background and lighting. Do not change the picture size or crop it.")
    lead = f"{expression.strip()} Keep this expression exactly. " if expression and expression.strip() else ""
    return (f"{lead}Image 1 is a frame of a video. Replace {target} in image 1 with the person shown in image 2"
            f"{f' ({look})' if look else ''}, wearing {outfit}. Keep image 1's exact pose, head angle, expression and gaze direction, "
            "camera framing, background and lighting. Do not change the picture size or crop it. Only change who the person is.")


STILLS_MAX = 8


def make_stills(project_id: str, pass_id: str, *, store_mod: Any, job_store: Any, release_wangp: Callable[[], None], prompt: str, count: int = 4,
                seed: int | None = None, comfy_runner_factory: Callable[..., Callable[[Path], Path]] | None = None) -> None:
    """Queue one job that edits the scene's first frame `count` times (one seed each) into candidate stills for Viggle.
    Each still is added to the pass as soon as it exists; the pass goes back to the status it had when the job ends."""
    project = store_mod.find(project_id)
    pass_ = next(p for p in project["passes"] if p["id"] == pass_id)
    scene = next(s for s in project["scenes"] if s["index"] == pass_["scene_index"])
    chunk = next(c for c in scene["chunks"] if c["index"] == pass_["chunk_index"])
    person = next(x for x in scene["people"] if x["id"] == pass_["person_id"])
    cast = next(c for c in project["cast"] if c["id"] == person["cast_id"])
    before = pass_.get("status") or "draft"
    base = int(seed if seed is not None else (pass_.get("seed") or project["settings"]["seed"]))
    seeds = [base + i * 101 for i in range(max(1, min(STILLS_MAX, int(count))))]
    out_dir = Path(store_mod.project_dir(project)) / "passes"
    out_dir.mkdir(parents=True, exist_ok=True)
    clip = out_dir / f"{pass_id}_stills_clip.mp4"
    source = out_dir / f"{pass_id}_still_source.png"

    def prepare(_dest: Path) -> Path:
        store_mod.update_pass(project_id, pass_id, status="running", still_error=None, activity="stills")
        scenes.extract_segment(project["source"]["path"], str(clip), scene["start_frame_src"], scene["end_frame_src"],
                               float(project["source"]["fps"]), chunk["start"], chunk["end"], WINDOW, extend=True)
        first_frame(str(clip), str(source))
        make = comfy_runner_factory or _qwen_runner
        qwen_w, qwen_h = store.size_for_short_side(project["source"]["width"], project["source"]["height"], 768)
        last = source
        for s in seeds:
            still_id = uuid.uuid4().hex[:8]
            params = {"prompt": prompt, "aspect": "wide", "width": qwen_w, "height": qwen_h, "seed": s,
                      "output_prefix": f"h3studio/still_{pass_id[:8]}", "source_paths": [str(source), cast["image_path"]]}
            made = make(params, release_wangp)(out_dir / f"{pass_id}_still_{still_id}_qwen")
            final = out_dir / f"{pass_id}_still_{still_id}.png"
            shutil.copyfile(made, final)
            current = next((p for p in store_mod.find(project_id)["passes"] if p["id"] == pass_id), {})
            entry = {"id": still_id, "path": str(final), "prompt": prompt, "seed": s, "created_at": time.time()}
            store_mod.update_pass(project_id, pass_id, stills=list(current.get("stills") or []) + [entry])
            last = final
        return last

    def on_done(status: str, output_path: Any = None, error: str | None = None, duration_seconds: float | None = None) -> None:
        store_mod.update_pass(project_id, pass_id, status=before, job_id=None, activity=None,
                              still_error=None if status == "done" else (error or "making the stills failed"))

    def queued(job_id: str) -> None:
        store_mod.update_pass(project_id, pass_id, status="queued", job_id=job_id, still_error=None, activity="stills")

    job_store.submit_callable(prepare, out_dir / "unused.png", on_done, on_queued=queued)


def _resize_png(src: str, dest: str, width: int, height: int) -> None:
    img = cv2.imdecode(__import__("numpy").fromfile(str(src), __import__("numpy").uint8), 1)
    img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    cv2.imencode(".png", img)[1].tofile(str(dest))


def start(project_id: str, pass_id: str, *, store_mod: Any, job_store: Any, release_wangp: Callable[[], None], size: int,
          seed: int | None = None, frame_path: str | None = None, expression: str = "", clip_path: str | None = None, slice_start: int = 0, sample_step: float | None = None,
          comfy_runner_factory: Callable[..., Callable[[Path], Path]] | None = None) -> None:
    """Queue the two jobs for one pass. Progress and the result are written to the pass like any other run."""
    project = store_mod.find(project_id)
    pass_ = next(p for p in project["passes"] if p["id"] == pass_id)
    scene = next(s for s in project["scenes"] if s["index"] == pass_["scene_index"])
    chunk = next(c for c in scene["chunks"] if c["index"] == pass_["chunk_index"])
    person = next(x for x in scene["people"] if x["id"] == pass_["person_id"])
    cast = next(c for c in project["cast"] if c["id"] == person["cast_id"])
    width, height = store.size_for_short_side(project["source"]["width"], project["source"]["height"], size)
    seed_value = int(seed if seed is not None else (pass_.get("seed") or project["settings"]["seed"]))
    out_dir = Path(store_mod.project_dir(project)) / "passes"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    clip = out_dir / f"{pass_id}_{run_id}_viggle_clip.mp4"
    raw_frame = out_dir / f"{pass_id}_{run_id}_viggle_frame_raw.png"
    edited = out_dir / f"{pass_id}_{run_id}_viggle_frame.png"
    raw_out = out_dir / f"{pass_id}_{run_id}_viggle_raw.mp4"
    output = out_dir / f"{pass_id}_{run_id}_viggle.mp4"
    t0 = time.time()

    def fail(message: str) -> None:
        store_mod.update_pass(project_id, pass_id, status="failed", error=message, job_id=None)

    def prepare(_dest: Path) -> Path:
        store_mod.update_pass(project_id, pass_id, status="running", error=None, method="viggle")
        if clip_path:  # a clip made elsewhere, e.g. several scenes joined; this pass's frames start at slice_start in it
            shutil.copyfile(clip_path, clip)
        else:
            scenes.extract_segment(project["source"]["path"], str(clip), scene["start_frame_src"], scene["end_frame_src"],
                                   float(project["source"]["fps"]), chunk["start"], chunk["end"], WINDOW, extend=True)
        if frame_path:
            _resize_png(frame_path, str(edited), width, height)
            return edited
        first_frame(str(clip), str(raw_frame))
        make = comfy_runner_factory or _qwen_runner
        qwen_w, qwen_h = store.size_for_short_side(project["source"]["width"], project["source"]["height"], 768)
        params = {"prompt": edit_prompt(person.get("target_description") or "the person", cast, expression), "aspect": "wide", "width": qwen_w,
                  "height": qwen_h, "seed": seed_value, "output_prefix": f"h3studio/viggle_{pass_id[:8]}",
                  "source_paths": [str(raw_frame), cast["image_path"]]}
        made = make(params, release_wangp)(edited.with_name(edited.stem + "_qwen"))
        _resize_png(str(made), str(edited), width, height)
        return edited

    def on_prepared(status: str, output_path: Any = None, error: str | None = None, duration_seconds: float | None = None) -> None:
        if status != "done":
            return fail(error or "preparing the edited frame failed")
        settings = build_settings(str(clip), str(edited), width, height, seed=seed_value, output_name=f"viggle_{pass_id[:8]}")

        def queued(job_id: str) -> None:
            store_mod.update_pass(project_id, pass_id, status="queued", job_id=job_id)

        def running() -> None:
            store_mod.update_pass(project_id, pass_id, status="running")

        job_store.submit(settings, raw_out, on_viggle_done, on_queued=queued, on_running=running)

    def on_viggle_done(status: str, output_path: Any = None, error: str | None = None, duration_seconds: float | None = None) -> None:
        if status != "done":
            return fail(error or "Viggle failed")
        try:
            if sample_step:  # the clip was slowed down: take it back to the scene's real speed
                scenes.sample_frames(str(raw_out), str(output), start=slice_start, step=sample_step, count=chunk["frames_24"])
            else:
                scenes.cut_frames(str(raw_out), str(output), slice_start, chunk["frames_24"])
            luma = runner.mean_luma(str(output))
            raw_frames = scenes.count_frames(str(raw_out))
            entry = {"id": run_id, "created_at": time.time(), "quality": "viggle", "width": width, "height": height, "seed": seed_value,
                     "seconds": round(time.time() - t0, 1), "mean_luma": round(luma, 1), "output_path": str(output), "raw_path": str(raw_out),
                     "prompt": "", "extra_loras": [], "control": None, "raw_frames": raw_frames - slice_start, "lead_used": slice_start, "method": "viggle",
                     "edited_frame": str(edited)}
            history = list(next((p for p in store_mod.find(project_id)["passes"] if p["id"] == pass_id), {}).get("history") or []) + [entry]
            store_mod.update_pass(project_id, pass_id, status="done", error=None, job_id=None, history=history, output_path=str(output),
                                  raw_path=str(raw_out), mean_luma=entry["mean_luma"], seconds=entry["seconds"], raw_frames=raw_frames - slice_start,
                                  lead_used=slice_start, trim_frames=None, method="viggle", viggle_frame=str(edited))
        except Exception as exc:  # noqa: BLE001
            fail(f"finishing the Viggle run failed: {exc}")

    def queued_a(job_id: str) -> None:
        store_mod.update_pass(project_id, pass_id, status="queued", job_id=job_id, method="viggle", error=None)

    job_store.submit_callable(prepare, out_dir / "unused.png", on_prepared, on_queued=queued_a)


def _qwen_runner(params: dict[str, Any], release_wangp: Callable[[], None]) -> Callable[[Path], Path]:
    from .. import comfy
    return comfy.make_runner(params, release_wangp)
