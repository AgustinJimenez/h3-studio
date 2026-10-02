"""Pre-flight checks for MiniMax H3 clips: frame grid, shot timing and a few prompt-quality
rules. Pure Python -- no GPU, no LLM, no network -- so it is safe to run on every edit.

Why it exists: H3 only renders frame counts on a 17k+5 grid, and WanGP silently rounds an
off-grid request DOWN (shared/utils/frame_scheduler.floor_frame_count). Across 133 past clips of
this app: 125 -> 124, 145 -> 141, 240 -> 226, while every on-grid request was honoured exactly.
The UI used to show the requested length, not the rendered one.

The rule set is re-derived from the open-source OpenH3-IR compiler's validator (github.com/ruashots/
open-h3-ir: grid.py and its R15 / P2 / cut-time rules), checked against WanGP's own source rather
than copied. Findings are advisory: WanGP's own validation stays the authority, so nothing here
blocks a generation. Description length is deliberately NOT checked: the UI's live word counter
(frontend/src/lib/wordCount.ts) already covers the guide's 350-500 words.
"""

from __future__ import annotations

import re
from typing import Any

from . import prompt

FPS = 24
GRID_STEP = 17
GRID_OFFSET = 5
MIN_FRAMES = 124   # 5.17 s; WanGP rejects a smaller sliding window ("must be at least 124")
MAX_FRAMES = 362   # 15.08 s; the top of the range the model was trained on
MIN_SHOT_SECONDS = 1.2
CANVAS_MULTIPLE = 32
MAX_PIXELS = 768 * 1344

# Garments/accessories we look for in a character's wardrobe notes (wardrobe drift between shots).
GARMENTS = (
    "t-shirt", "tee", "shirt", "jacket", "coat", "hoodie", "sweater", "sweatshirt", "dress", "skirt",
    "jeans", "trousers", "pants", "sweatpants", "shorts", "boots", "shoes", "sneakers", "sandals",
    "glasses", "hat", "cap", "suit", "tie", "scarf", "gloves",
)


# ----------------------------------------------------------------------------- frame grid

def legal_lengths(lo: int = MIN_FRAMES, hi: int = MAX_FRAMES) -> list[int]:
    """Every frame count H3 can render inside [lo, hi]: n % 17 == 5."""
    return [n for n in range(lo, hi + 1) if (n - GRID_OFFSET) % GRID_STEP == 0]


def rendered_frames(requested: int) -> int:
    """Frames WanGP actually renders for a single-window clip: the request rounded DOWN onto the grid."""
    n = max(GRID_OFFSET, int(requested))
    return ((n - GRID_OFFSET) // GRID_STEP) * GRID_STEP + GRID_OFFSET


def seconds(frames: int) -> float:
    return frames / FPS


# ----------------------------------------------------------------------------- shot parsing

_SHOT_MARKER = re.compile(r"\[Shot\s+(\d+)\]")
_CUT_TIME = re.compile(r"\s*At\s+(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?", re.I)


def split_shots(text: str) -> list[tuple[int, str]]:
    """[(shot number, the text after its '[Shot N]' marker up to the next marker)]."""
    marks = list(_SHOT_MARKER.finditer(text or ""))
    return [
        (int(m.group(1)), text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)])
        for i, m in enumerate(marks)
    ]


def cut_time(block: str) -> float | None:
    """The 'At MM:SS.mmm' that must open a shot after the first, in seconds (None if absent)."""
    m = _CUT_TIME.match(block)
    if not m:
        return None
    millis = int((m.group(3) or "0").ljust(3, "0"))
    return int(m.group(1)) * 60 + int(m.group(2)) + millis / 1000


# ----------------------------------------------------------------------------- rules

def _finding(code: str, level: str, message: str) -> dict[str, str]:
    return {"code": code, "level": level, "message": message}


def _length_findings(requested: int, rendered: int) -> list[dict[str, str]]:
    out = []
    if requested < MIN_FRAMES:
        out.append(_finding("G2", "error", f"video_length {requested} is below H3's minimum of {MIN_FRAMES} frames "
                                            f"({seconds(MIN_FRAMES):.2f}s); WanGP rejects it."))
    elif rendered != requested:
        up = rendered + GRID_STEP
        out.append(_finding("G1", "warn", f"video_length {requested} is not on H3's 17k+5 grid, so WanGP renders {rendered} "
                                          f"frames ({seconds(rendered):.2f}s), not {requested}. Nearest legal lengths: "
                                          f"{rendered} or {up} ({seconds(up):.2f}s)."))
    if requested > MAX_FRAMES:
        out.append(_finding("G3", "info", f"video_length {requested} is above the {MAX_FRAMES}-frame ({seconds(MAX_FRAMES):.2f}s) "
                                          "range H3 was trained on; it renders, but slower and less reliably."))
    return out


def _shot_findings(shot_prompt: str, rendered: int) -> list[dict[str, str]]:
    shots = split_shots(shot_prompt)
    if len(shots) < 2:
        return []
    out, previous, total = [], 0.0, seconds(rendered)
    for number, block in shots[1:]:
        t = cut_time(block)
        if t is None:
            out.append(_finding("T1", "warn", f"[Shot {number}] doesn't open with 'At MM:SS.mmm', so H3 can't place the cut."))
            continue
        if t < previous + MIN_SHOT_SECONDS:
            out.append(_finding("T2", "warn", f"[Shot {number}] cuts at {t:.3f}s, only {t - previous:.2f}s after the previous "
                                              f"cut; a shot needs to hold at least {MIN_SHOT_SECONDS}s."))
        elif t > total - MIN_SHOT_SECONDS:
            out.append(_finding("T3", "warn", f"[Shot {number}] cuts at {t:.3f}s, leaving under {MIN_SHOT_SECONDS}s before the "
                                              f"clip ends at {total:.2f}s."))
        previous = max(previous, t)
    return out


def _mentions(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}s?(?![\w-])", text, re.I) is not None


def _wardrobe_findings(shot_prompt: str, characters: list[dict[str, Any]]) -> list[dict[str, str]]:
    shots = split_shots(shot_prompt)
    if len(shots) < 2:
        return []
    out = []
    for index, character in enumerate(characters, start=1):
        if character.get("kind") == "environment":
            continue
        garments = [g for g in GARMENTS if _mentions(character.get("wardrobe_notes") or "", g)]
        name = (character.get("name") or "").strip()
        if not garments or not name:
            continue
        for number, block in shots:
            names_them = _mentions(block, name) or f"<Subject {index}>" in block
            if names_them and not any(_mentions(block, g) for g in garments):
                out.append(_finding("W1", "warn", f"[Shot {number}] names {name} but not their outfit ({', '.join(garments[:3])}"
                                                  "...); wardrobe drifts between shots when it is only stated once."))
    return out


def _settings_findings(settings: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    m = re.fullmatch(r"(\d+)x(\d+)", str(settings.get("resolution") or ""))
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w % CANVAS_MULTIPLE or h % CANVAS_MULTIPLE:
            out.append(_finding("C1", "warn", f"resolution {w}x{h} isn't a multiple of {CANVAS_MULTIPLE} on both sides."))
        if w * h > MAX_PIXELS:
            out.append(_finding("C2", "info", f"resolution {w}x{h} is above the ~{MAX_PIXELS / 1e6:.2f} MP (768x1344) the model was "
                                              "trained around; expect the memory/speed cliff seen at 1080p."))
    return out


def lint_clip(video: dict[str, Any], clip: dict[str, Any], previous_clip: dict[str, Any] | None = None,
              bridge_end_frame_path: str | None = None) -> dict[str, Any]:
    """Everything worth knowing about a clip before spending minutes of GPU time on it."""
    requested = int(clip.get("video_length") or prompt.DEFAULT_VIDEO_LENGTH)
    rendered = rendered_frames(requested)
    findings = _length_findings(requested, rendered)
    shot_prompt = clip.get("shot_prompt") or ""
    findings += _shot_findings(shot_prompt, rendered)
    findings += _wardrobe_findings(shot_prompt, prompt.active_characters_for_clip(video, clip))
    try:
        settings = prompt.build_generation_settings(video, clip, previous_clip, bridge_end_frame_path)
    except Exception as exc:  # a lint must never take generation down with it
        findings.append(_finding("P0", "error", f"the prompt can't be built: {exc}"))
    else:
        findings += _settings_findings(settings)
    return {
        "requested_frames": requested,
        "rendered_frames": rendered,
        "rendered_seconds": round(seconds(rendered), 3),
        "findings": findings,
    }
