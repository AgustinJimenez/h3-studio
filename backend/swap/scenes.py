"""Scene detection, frame-grid padding and chunking for the swap feature.

Pure arithmetic (grid_length, frames_at_24, split_chunks, build_scenes) plus the
ffmpeg-backed pieces (detect_cuts, extract_segment, count_frames). No GPU, no ComfyUI.

H3 only renders lengths with frames % 17 == 5 (5, 22, 39, ..., 124, ..., 362) at 24 fps, and the
ComfyUI loader does not resample, so every segment is converted to 24 fps and padded by holding its
last frame up to the next legal length before it is sent. The result is trimmed back afterwards.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

import cv2
import imageio_ffmpeg
import numpy as np

FPS = 24
CUT_THRESHOLD = 40.0  # mean abs gray difference (0-255) between consecutive frames; real cuts 44-84, fast pans 21-32
_PROBE_WIDTH = 96


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def grid_length(n: int) -> int:
    """Smallest legal H3 frame count >= n (frames % 17 == 5), minimum 5."""
    n = max(5, int(n))
    return ((n - 5 + 16) // 17) * 17 + 5


MIN_FRAMES = 124  # H3's trained range starts at 124 frames (5.17 s); shorter clips make it fall back on the reference picture


def render_length(n: int) -> int:
    """Frames to ask H3 for when a chunk has n real frames: the next legal length, never below the trained minimum."""
    return max(MIN_FRAMES, grid_length(n))


def frames_at_24(n_src: int, fps_src: float) -> int:
    return max(1, round(n_src * FPS / fps_src))


def split_chunks(n: int, max_chunk: int) -> list[tuple[int, int]]:
    """Near-equal chunks of at most max_chunk frames, as (start, end) inclusive, scene-local.
    The first n % k chunks are one frame longer; nothing is skipped or repeated."""
    k = max(1, -(-n // max_chunk))
    base, rem = divmod(n, k)
    out: list[tuple[int, int]] = []
    start = 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        out.append((start, start + size - 1))
        start += size
    return out


def count_frames(path: str) -> int:
    """Exact decoded frame count (container metadata is unreliable after re-encoding)."""
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-", "-stats"],
                       capture_output=True, text=True)
    hits = re.findall(r"frame=\s*(\d+)", r.stderr)
    if not hits:
        raise RuntimeError(f"could not count frames in {path}: {r.stderr[-300:]}")
    return int(hits[-1])


def detect_cuts(path: str, threshold: float = CUT_THRESHOLD) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    probe_h = max(2, int(round(_PROBE_WIDTH * height / max(1, width))) // 2 * 2)
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-map", "0:v:0",
                        "-vf", f"scale={_PROBE_WIDTH}:{probe_h},format=gray", "-f", "rawvideo", "-"], capture_output=True)
    raw = np.frombuffer(r.stdout, np.uint8)
    n = len(raw) // (_PROBE_WIDTH * probe_h)
    frames = raw[: n * _PROBE_WIDTH * probe_h].reshape(n, probe_h, _PROBE_WIDTH).astype(np.float32)
    diffs = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2)) if n > 1 else np.array([])
    cuts = [int(i) + 1 for i, d in enumerate(diffs) if d > threshold]
    info = subprocess.run([ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
    return {"fps": fps, "frames": int(n), "width": width, "height": height, "cuts": cuts, "has_audio": "Audio:" in info}


def build_scenes(cuts: list[int], frames: int, fps: float, max_chunk: int) -> list[dict[str, Any]]:
    starts = [0] + list(cuts)
    ends = [c - 1 for c in cuts] + [frames - 1]
    out = []
    for i, (a, b) in enumerate(zip(starts, ends)):
        n24 = frames_at_24(b - a + 1, fps)
        chunks = [{"index": j, "start": s, "end": e, "frames_24": e - s + 1, "padded_frames": render_length(e - s + 1)}
                  for j, (s, e) in enumerate(split_chunks(n24, max_chunk))]
        out.append({"index": i, "start_frame_src": a, "end_frame_src": b, "frames_24": n24, "chunks": chunks})
    return out


def extract_segment(src: str, dest: str, start_src: int, end_src: int, fps_src: float,
                    chunk_start: int, chunk_end: int, pad_to: int | None, extend: bool = False, lead: int = 0) -> int:
    """Write a 24 fps, audio-less mp4 of one chunk of one scene; returns the lead-in actually used.

    start_src/end_src: the scene's source frames (inclusive). chunk_start/chunk_end: scene-local 24 fps
    frames. pad_to: reach exactly this many frames (None = the chunk's own length). The padding holds the last frame, or with
    extend=True continues with the real footage that follows the chunk (the next scenes) and only holds at the end of the file.
    lead: 24 fps frames of real footage to put BEFORE the chunk (what precedes the scene), so the model's odd first frame lands
    there and not on the scene; fewer if the file does not have that much before it. The caller cuts the lead-in off again.
    """
    lead_src = int(-(-lead * fps_src // FPS)) if lead > 0 else 0
    sel_start = max(0, start_src - lead_src)
    lead_avail = round((start_src - sel_start) * FPS / fps_src)
    lead_used = min(lead, lead_avail) if lead > 0 else 0
    n = chunk_end - chunk_start + 1
    total = max(lead_used + n, pad_to) if pad_to is not None else lead_used + n
    scene24 = f"{dest}.scene24.mp4"
    if extend:
        # enough source frames to cover the chunk and its padding (the end of the file simply ends it)
        end_src = start_src + int(-(-(chunk_start + total - lead_used) * fps_src // FPS)) + 2
    # Step 1: the lead-in, the scene (and, extended, what follows it) at a constant 24 fps (ffmpeg's fps filter resamples).
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(src), "-vf",
                        f"select='between(n\\,{sel_start}\\,{end_src})',setpts=N/({fps_src}*TB),fps={FPS}",
                        "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", scene24],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed converting a scene to 24 fps: {r.stderr[-400:]}")
    # Step 2: pick the frames one by one and hold the last to reach the padded length. ffmpeg's trim/tpad filters gave wrong
    # frame counts (padding silently dropped), so the count is done here.
    begin = lead_avail + chunk_start - lead_used  # index in scene24 where the written clip starts
    chunk_last = lead_avail + chunk_end
    cap = cv2.VideoCapture(scene24)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    enc = subprocess.Popen([ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p",
                            str(dest)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last = None
    written = 0
    try:
        index = 0
        while written < total:
            if index <= chunk_last or extend:
                ok, frame = cap.read()
                if not ok:
                    frame = last  # the footage ended early: hold the last frame
                index += 1
                if frame is None:
                    break
                if index - 1 < begin:
                    continue
                last = frame
            else:
                frame = last  # padding: hold the chunk's last frame
            if frame is None:
                break
            enc.stdin.write(frame.tobytes())
            written += 1
    finally:
        cap.release()
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
        try:
            os.remove(scene24)
        except OSError:
            pass
    if code != 0 or written != total:
        raise RuntimeError(f"segment extraction wrote {written}/{total} frames: {err[-300:]}")
    return lead_used


def cut_frames(src: str, dest: str, start: int, count: int) -> None:
    """Write frames start..start+count-1 of `src` (exactly: ffmpeg's trim filters miscounted)."""
    cap = cv2.VideoCapture(str(src))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    enc = subprocess.Popen([ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS),
                            "-i", "-", "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(dest)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    written = 0
    try:
        index = 0
        while written < count:
            ok, frame = cap.read()
            if not ok:
                break
            index += 1
            if index - 1 < start:
                continue
            enc.stdin.write(frame.tobytes())
            written += 1
    finally:
        cap.release()
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0 or written != count:
        raise RuntimeError(f"cut wrote {written}/{count} frames: {err[-300:]}")


def make_edge_video(src: str, dest: str, low: int = 40, high: int = 110) -> None:
    """A control video for H3's Fun ControlNet: white Canny edges on black, same frames and size as `src`."""
    cap = cv2.VideoCapture(str(src))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    enc = subprocess.Popen([ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS),
                            "-i", "-", "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(dest)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    kernel = np.ones((2, 2), np.uint8)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), 0), low, high)
            edges = cv2.dilate(edges, kernel)
            enc.stdin.write(cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR).tobytes())
    finally:
        cap.release()
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0:
        raise RuntimeError(f"edge video encoding failed: {err[-300:]}")


def sample_frames(src: str, dest: str, start: float, step: float, count: int) -> None:
    """`count` frames of `src` at start, start+step, start+2*step... (rounded; the last frame is held past the end).

    Takes a slowed-down render back to real speed: with a slowdown of S, step = S to land on the original frames."""
    cap = cv2.VideoCapture(str(src))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError(f"no frames in {src}")
    h, w = frames[0].shape[:2]
    enc = subprocess.Popen([ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS),
                            "-i", "-", "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(dest)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for k in range(count):
            enc.stdin.write(frames[min(len(frames) - 1, int(round(start + k * step)))].tobytes())
    finally:
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0:
        raise RuntimeError(f"sampling failed: {err[-300:]}")
