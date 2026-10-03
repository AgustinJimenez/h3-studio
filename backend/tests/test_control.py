from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from backend import control
from backend.swap import scenes


def _halves(path: Path, frames: int = 60, size: str = "192x320", fps: int = 24) -> str:
    """The first half white, the second half black: an extracted range tells which half it came from."""
    ff = scenes.ffmpeg_exe()
    parts = []
    for i, color in enumerate(("white", "black")):
        p = path.parent / f"{path.stem}_{i}.mp4"
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r={fps}", "-frames:v", str(frames // 2),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
        parts.append(p)
    lst = path.parent / f"{path.stem}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(path)], check=True)
    return str(path)


def _mean_luma(path: str) -> float:
    cap = cv2.VideoCapture(path)
    vals = []
    ok, f = cap.read()
    while ok:
        vals.append(float(f.mean()))
        ok, f = cap.read()
    cap.release()
    return float(np.mean(vals))


def test_a_short_range_is_stretched_to_the_h3_minimum_and_resized():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "src.mp4", 200)  # frames 0-99 white, 100-199 black
        info = control.build_control_clip(src, 100, 139, 24.0, 64, 96, str(d / "ctl.mp4"))
        assert info["source_frames"] == 40 and info["frames_24"] == 40 and info["frames"] == 124 and info["stretched"] is True
        assert scenes.count_frames(str(d / "ctl.mp4")) == 124
        assert control.video_info(str(d / "ctl.mp4")) == {"frames": 124, "width": 64, "height": 96, "fps": 24.0}
        assert _mean_luma(str(d / "ctl.mp4")) < 40  # the black half


def test_a_long_enough_range_is_kept_as_it_is_and_only_the_range_is_used():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "src.mp4", 300)  # 0-149 white, 150-299 black
        info = control.build_control_clip(src, 0, 139, 24.0, 64, 96, str(d / "ctl.mp4"))
        assert info["frames"] == 140 and info["stretched"] is False
        assert _mean_luma(str(d / "ctl.mp4")) > 200  # the white half only


def test_other_frame_rates_are_brought_to_24_fps():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "src30.mp4", 300, fps=30)  # ten seconds
        info = control.build_control_clip(src, 0, 149, 30.0, 64, 96, str(d / "ctl.mp4"))  # five seconds of 30 fps = 120 frames at 24
        assert info["frames_24"] == 120 and info["frames"] == 124 and info["stretched"] is True


def test_a_target_length_fits_the_clip_exactly_in_either_direction():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "src.mp4", 300)
        longer = control.build_control_clip(src, 0, 129, 24.0, 64, 96, str(d / "a.mp4"), frames=141)  # 130 frames slowed to 141
        assert longer["frames"] == 141 and longer["stretched"] is True and scenes.count_frames(str(d / "a.mp4")) == 141
        shorter = control.build_control_clip(src, 0, 129, 24.0, 64, 96, str(d / "b.mp4"), frames=124)  # 130 frames sped up to 124
        assert shorter["frames"] == 124 and shorter["stretched"] is True and scenes.count_frames(str(d / "b.mp4")) == 124
        same = control.build_control_clip(src, 0, 123, 24.0, 64, 96, str(d / "c.mp4"), frames=124)
        assert same["frames"] == 124 and same["stretched"] is False


def test_the_context_tail_is_the_last_frames_of_the_previous_clip():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "prev.mp4", 60)  # frames 0-29 white, 30-59 black
        control.context_tail(src, str(d / "ctx.mp4"), 22)
        assert scenes.count_frames(str(d / "ctx.mp4")) == 22
        assert _mean_luma(str(d / "ctx.mp4")) < 40  # the end of the clip, not its start
        short = control.context_tail(src, str(d / "all.mp4"), 500)  # more than the clip has: the whole clip
        assert short == 60 and scenes.count_frames(str(d / "all.mp4")) == 60


def test_the_lead_in_is_the_context_frames_when_set_and_the_whole_previous_clip_otherwise():
    assert control.lead_in_seconds(5, 5.17) == 5 / 24  # a continuation that was given the previous clip's last 5 frames
    assert control.lead_in_seconds(None, 5.17) == 5.17  # a continuation of the whole previous clip
    assert control.lead_in_seconds(0, 5.17) == 5.17


def test_the_own_segment_drops_exactly_the_lead_in_frames():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _halves(d / "cont.mp4", 60)  # 24 fps: frames 0-29 white, 30-59 black
        assert control.own_segment(src, str(d / "own.mp4"), 30 / 24) is True
        assert scenes.count_frames(str(d / "own.mp4")) == 30
        assert _mean_luma(str(d / "own.mp4")) < 40  # only the part after the lead-in


def _clip(order, **kw):
    return {"order": order, "status": "done", "output_path": f"clip{order}.mp4", "continue_from_previous": False, "continuation_keep_frames": None,
            "own_segment_path": None, **kw}


def test_clips_with_no_continuation_are_all_joined():
    paths, mixed = control.segments_to_join([_clip(0), _clip(1), _clip(2)])
    assert paths == ["clip0.mp4", "clip1.mp4", "clip2.mp4"] and mixed is False


def test_a_whole_clip_continuation_already_contains_the_clip_before_it():
    clips = [_clip(0), _clip(1), _clip(2, continue_from_previous=True)]
    paths, mixed = control.segments_to_join(clips)
    assert paths == ["clip0.mp4", "clip2.mp4"] and mixed is False  # clip 2's file holds clip 1 as its lead-in


def test_a_continuation_with_context_frames_adds_only_its_own_part_and_keeps_the_clip_before():
    clips = [_clip(0), _clip(1), _clip(2, continue_from_previous=True, continuation_keep_frames=5, own_segment_path="own2.mp4")]
    paths, mixed = control.segments_to_join(clips)
    assert paths == ["clip0.mp4", "clip1.mp4", "own2.mp4"] and mixed is True


def test_clips_that_are_not_done_are_left_out():
    paths, _ = control.segments_to_join([_clip(0), _clip(1, status="failed"), _clip(2)])
    assert paths == ["clip0.mp4", "clip2.mp4"]


def test_video_info_of_a_missing_file_is_none():
    assert control.video_info("nope.mp4") is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
