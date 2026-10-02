"""Join the finished scene chunks and lay the original audio back under them."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

import cv2

from .scenes import FPS, count_frames, ffmpeg_exe


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed {what}: {r.stderr[-400:]}")


def _size(path: str) -> tuple[int, int]:
    cap = cv2.VideoCapture(str(path))
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()


def join_videos(paths: list[str], dest: str, size: tuple[int, int] | None = None) -> None:
    """Concatenate clips into one 24 fps, audio-less mp4 at `size` (default: the first clip's size).

    Clips of another size are scaled first: concatenating mixed sizes straight through made ffmpeg drop
    frames at the joins (a swapped 704x1248 clip between 720x1280 originals lost 3 of 580 frames)."""
    if not paths:
        raise ValueError("nothing to join")
    size = size or _size(paths[0])
    with tempfile.TemporaryDirectory() as d:
        parts: list[str] = []
        for i, p in enumerate(paths):
            if _size(p) == tuple(size):
                parts.append(p)
                continue
            fixed = os.path.join(d, f"fit_{i}.mp4")
            _run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(p), "-an", "-vf", f"scale={size[0]}:{size[1]}:flags=lanczos,setsar=1",
                  "-fps_mode", "passthrough", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", fixed], "resizing a clip")
            parts.append(fixed)
        listing = os.path.join(d, "list.txt")
        with open(listing, "w", encoding="utf-8") as fh:
            for p in parts:
                fh.write("file '" + os.path.abspath(p).replace("\\", "/").replace("'", "'\\''") + "'\n")
        _run([ffmpeg_exe(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-an", "-fps_mode", "passthrough",
              "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dest)], "joining scenes")


def add_audio(video: str, audio_source: str, dest: str) -> bool:
    info = subprocess.run([ffmpeg_exe(), "-i", str(audio_source)], capture_output=True, text=True).stderr
    if "Audio:" not in info:
        shutil.copyfile(video, dest)
        return False
    # The picture decides the length: audio that runs short is padded with silence (a plain "-shortest" cut the end of the video).
    seconds = count_frames(video) / FPS
    _run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(video), "-i", str(audio_source), "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "aac", "-af", "apad", "-t", f"{seconds:.4f}", str(dest)], "adding audio")
    return True


def assemble_project(segments: list[list[str]], source: str, dest: str) -> dict[str, Any]:
    flat = [p for scene in segments for p in scene]
    tmp = f"{dest}.joined.mp4"
    try:
        join_videos(flat, tmp, size=_size(source))
        audio = add_audio(tmp, source, dest)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    frames = count_frames(dest)
    return {"frames": frames, "seconds": frames / FPS, "audio": audio}
