"""Control videos: the depth guide H3 follows for a clip's camera movement and blocking.

A control video can come from anywhere (a Blender previs, a scene of an existing video). H3 renders at least 124 frames, so a
short stretch of footage is slowed down to that length rather than padded with footage that does not belong to the shot."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2

from .swap import scenes

FPS = 24
MIN_FRAMES = scenes.MIN_FRAMES  # H3's shortest clip


def _run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-400:]}")


def build_control_clip(src: str, start_src: int, end_src: int, fps_src: float, width: int, height: int, dest: str, *,
                       min_frames: int = MIN_FRAMES, frames: int | None = None) -> dict[str, Any]:
    """Writes `dest`: source frames start..end (inclusive) at 24 fps, scaled to width x height. With `frames` the clip is
    slowed down or sped up to exactly that many frames (so it matches the clip it guides); otherwise one shorter than
    `min_frames` is slowed down to that. Returns what was done."""
    if end_src < start_src:
        raise ValueError("the range ends before it starts")
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    ff = scenes.ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        mid = str(Path(tmp) / "range.mp4")
        _run([ff, "-v", "error", "-y", "-i", str(src), "-vf",
              f"select='between(n,{int(start_src)},{int(end_src)})',setpts=N/FRAME_RATE/TB,fps={FPS},scale={int(width)}:{int(height)}:flags=lanczos",
              "-an", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", mid])
        n = scenes.count_frames(mid)
        target = int(frames) if frames else max(n, min_frames)
        if n == target:
            Path(dest).write_bytes(Path(mid).read_bytes())
            return {"source_frames": end_src - start_src + 1, "frames_24": n, "frames": n, "stretched": False}
        _run([ff, "-v", "error", "-y", "-i", mid, "-vf", f"setpts=PTS*{target}/{n},fps={FPS}", "-frames:v", str(target), "-an",
              "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(dest)])
    return {"source_frames": end_src - start_src + 1, "frames_24": n, "frames": scenes.count_frames(str(dest)), "stretched": True}


def context_tail(src: str, dest: str, keep: int) -> int:
    """Writes the LAST `keep` frames of `src` to `dest` (all of it when it is shorter) and returns how many it holds.
    A continuation clip must start from where the previous one ends: WanGP's own `keep_frames_video_source` keeps the FIRST frames."""
    total = scenes.count_frames(str(src))
    n = min(int(keep), total)
    scenes.cut_frames(str(src), str(dest), total - n, n)
    return n


def lead_in_seconds(keep_frames: int | None, previous_seconds: float, fps: int = FPS) -> float:
    """How much of a continuation clip is inherited from the previous clip: the context frames it was given, or all of the
    previous clip when it was continued whole."""
    return keep_frames / fps if keep_frames else previous_seconds


def own_segment(src: str, dest: str, start_seconds: float) -> bool:
    """Writes the part of `src` after the first `start_seconds` (re-encoded, so the cut is frame accurate)."""
    r = subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", "-ss", f"{start_seconds:.4f}", "-i", str(src), "-c:v", "libx264", "-crf", "14",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(dest)], capture_output=True, text=True)
    return r.returncode == 0 and Path(dest).exists()


def segments_to_join(clips: list[dict[str, Any]]) -> tuple[list[str], bool]:
    """The files that make the whole video, in order, and whether any of them is a trimmed part (so the join must re-encode).
    A continuation of the WHOLE previous clip already contains that clip, so the clip before it is skipped; one given only
    context frames holds just those, so the clip before it stays and only the new part (its own segment) is added."""
    done = {c["order"]: c for c in clips if c.get("status") == "done" and c.get("output_path")}
    paths: list[str] = []
    mixed = False
    for order in sorted(done):
        clip = done[order]
        nxt = done.get(order + 1)
        if nxt and nxt.get("continue_from_previous") and not nxt.get("continuation_keep_frames"):
            continue
        if clip.get("continue_from_previous") and clip.get("continuation_keep_frames") and clip.get("own_segment_path"):
            paths.append(clip["own_segment_path"])
            mixed = True
        else:
            paths.append(clip["output_path"])
    return paths, mixed


def video_info(path: str | None) -> dict[str, Any] | None:
    """Frame count, size and fps of a video file, or None when it is missing or unreadable."""
    if not path or not Path(path).exists():
        return None
    cap = cv2.VideoCapture(str(path))
    try:
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()
    if not frames or not width:
        return None
    return {"frames": frames, "width": width, "height": height, "fps": round(fps, 3)}
