from __future__ import annotations

import os
import subprocess
import tempfile

from backend.swap import scenes


def test_grid_length():
    got = [scenes.grid_length(n) for n in (1, 5, 6, 22, 23, 35, 69, 124, 125, 243, 249)]
    assert got == [5, 5, 22, 22, 39, 39, 73, 124, 141, 243, 260]


def test_frames_at_24():
    assert scenes.frames_at_24(44, 30) == 35
    assert scenes.frames_at_24(311, 30) == 249
    assert scenes.frames_at_24(24, 24) == 24
    assert scenes.frames_at_24(0, 30) == 1


def _sizes(chunks):
    return [e - s + 1 for s, e in chunks]


def test_split_chunks_edges():
    assert scenes.split_chunks(124, 124) == [(0, 123)]
    assert scenes.split_chunks(125, 124) == [(0, 62), (63, 124)]
    c = scenes.split_chunks(249, 243)
    assert _sizes(c) == [125, 124] and c[0][0] == 0 and c[-1][1] == 248 and c[1][0] == c[0][1] + 1
    assert _sizes(scenes.split_chunks(243, 243)) == [243]
    assert _sizes(scenes.split_chunks(244, 243)) == [122, 122]
    big = scenes.split_chunks(700, 124)
    assert sum(_sizes(big)) == 700 and max(_sizes(big)) <= 124


def _make_video(path, segs, fps=30, size="96x160"):
    # segs: [(seconds, colour)] -> solid-colour shots, so every join is a hard cut
    inputs = []
    for sec, color in segs:
        inputs += ["-f", "lavfi", "-t", str(sec), "-i", f"color=c={color}:s={size}:r={fps}"]
    flt = "".join(f"[{i}:v]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]"
    subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", *inputs, "-filter_complex", flt, "-map", "[v]",
                    "-pix_fmt", "yuv420p", path], check=True)


def test_detect_cuts_and_build_scenes():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    _make_video(p, [(1.0, "white"), (1.0, "black"), (1.0, "white")])
    info = scenes.detect_cuts(p)
    assert info["frames"] == 90 and round(info["fps"]) == 30 and info["has_audio"] is False
    assert info["cuts"] == [30, 60]
    sc = scenes.build_scenes(info["cuts"], info["frames"], info["fps"], 124)
    assert [(s["start_frame_src"], s["end_frame_src"], s["frames_24"]) for s in sc] == [(0, 29, 24), (30, 59, 24), (60, 89, 24)]
    assert sc[0]["chunks"][0]["padded_frames"] == 124 and sc[0]["chunks"][0]["frames_24"] == 24  # H3 is trained on 124+ frames


def test_detect_cuts_ignores_soft_changes():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    _make_video(p, [(1.0, "gray"), (1.0, "0x909090")])  # tiny brightness step, not a cut
    assert scenes.detect_cuts(p)["cuts"] == []


def test_extract_segment_pads_and_trims():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    out = os.path.join(d, "o.mp4")
    _make_video(p, [(1.0, "white"), (1.0, "black")])
    scenes.extract_segment(p, out, 30, 59, 30.0, 0, 23, 39)
    assert scenes.count_frames(out) == 39
    scenes.extract_segment(p, out, 30, 59, 30.0, 0, 23, None)
    assert scenes.count_frames(out) == 24


def _luma_of_frames(path):
    import cv2
    cap = cv2.VideoCapture(path)
    out = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out.append(round(float(frame.mean())))
    cap.release()
    return out


def test_extract_segment_picks_the_right_frames_and_holds_the_last():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    out = os.path.join(d, "o.mp4")
    # one scene at 30 fps: 0.5 s white, 0.5 s black, 0.5 s white, 0.5 s black (15 src frames each = 12 frames at 24 fps)
    _make_video(p, [(0.5, "white"), (0.5, "black"), (0.5, "white"), (0.5, "black")])
    scenes.extract_segment(p, out, 0, 59, 30.0, 0, 11, None)      # the first white block only
    assert all(v > 200 for v in _luma_of_frames(out)) and len(_luma_of_frames(out)) == 12
    scenes.extract_segment(p, out, 0, 59, 30.0, 12, 23, None)     # the first black block only
    assert all(v < 50 for v in _luma_of_frames(out)) and len(_luma_of_frames(out)) == 12
    scenes.extract_segment(p, out, 0, 59, 30.0, 12, 23, 22)       # black block padded: the hold is black too
    lumas = _luma_of_frames(out)
    assert len(lumas) == 22 and all(v < 50 for v in lumas)
    scenes.extract_segment(p, out, 0, 59, 30.0, 6, 17, None)      # straddles white -> black: 6 white then 6 black
    lumas = _luma_of_frames(out)
    assert len(lumas) == 12 and all(v > 200 for v in lumas[:6]) and all(v < 50 for v in lumas[6:])


def test_render_length_is_never_below_the_trained_minimum():
    assert [scenes.render_length(n) for n in (1, 10, 24, 123, 124, 125, 243)] == [124, 124, 124, 124, 124, 141, 243]


def test_extend_pads_with_the_real_footage_that_follows_not_a_frozen_frame():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    out = os.path.join(d, "o.mp4")
    _make_video(p, [(1.0, "white"), (1.0, "black")])  # the scene is the white second; black follows it
    scenes.extract_segment(p, out, 0, 29, 30.0, 0, 23, 39)  # default: hold the last (white) frame
    assert all(v > 200 for v in _luma_of_frames(out)) and len(_luma_of_frames(out)) == 39
    scenes.extract_segment(p, out, 0, 29, 30.0, 0, 23, 39, extend=True)
    lumas = _luma_of_frames(out)
    assert len(lumas) == 39 and all(v > 200 for v in lumas[:24]) and all(v < 50 for v in lumas[26:])
    # at the end of the file there is nothing left to follow: the last frame is held
    scenes.extract_segment(p, out, 30, 59, 30.0, 0, 23, 39, extend=True)
    lumas = _luma_of_frames(out)
    assert len(lumas) == 39 and all(v < 50 for v in lumas)


def test_edge_video_keeps_frames_and_size_and_is_black_with_white_edges():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "t.mp4")
    out = os.path.join(d, "e.mp4")
    subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=128x96:rate=24:duration=1",
                    "-pix_fmt", "yuv420p", src], check=True)
    scenes.make_edge_video(src, out)
    import cv2
    cap = cv2.VideoCapture(out)
    n, w, h = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, frame = cap.read()
    cap.release()
    assert scenes.count_frames(out) == 24 and (w, h) == (128, 96)
    assert (frame > 200).mean() > 0.01 and (frame < 40).mean() > 0.5  # mostly black, with white lines


def test_lead_in_starts_the_clip_before_the_scene_and_cut_frames_removes_it():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "v.mp4")
    out = os.path.join(d, "o.mp4")
    cut = os.path.join(d, "c.mp4")
    _make_video(p, [(1.0, "white"), (1.0, "black"), (1.0, "white")])  # the scene is the black second (src frames 30-59)
    used = scenes.extract_segment(p, out, 30, 59, 30.0, 0, 23, 39, extend=True, lead=6)
    lumas = _luma_of_frames(out)
    assert used == 6 and len(lumas) == 39
    assert all(v > 200 for v in lumas[:6]) and all(v < 50 for v in lumas[6:30]) and all(v > 200 for v in lumas[30:])
    scenes.cut_frames(out, cut, 6, 24)
    assert len(_luma_of_frames(cut)) == 24 and all(v < 50 for v in _luma_of_frames(cut))
    # a scene at the very start of the file has nothing before it
    assert scenes.extract_segment(p, out, 0, 29, 30.0, 0, 23, 39, extend=True, lead=6) == 0


def test_sample_frames_picks_every_nth_frame_back_down_to_real_speed():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "ramp.mp4")
    out = os.path.join(d, "s.mp4")
    import cv2
    enc = subprocess.Popen([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "64x64", "-r", "24",
                            "-i", "-", "-c:v", "libx264", "-crf", "5", "-pix_fmt", "yuv420p", src], stdin=subprocess.PIPE)
    import numpy as np
    for i in range(100):
        enc.stdin.write(np.full((64, 64, 3), 20 + i * 2, np.uint8).tobytes())  # brightness rises 2 per frame
    enc.stdin.close()
    enc.wait()
    scenes.sample_frames(src, out, start=10, step=10.0, count=5)  # frames 10, 20, 30, 40, 50
    lumas = _luma_of_frames(out)
    assert len(lumas) == 5 and all(abs(lumas[i] - (20 + (10 + 10 * i) * 2)) <= 6 for i in range(5))
    scenes.sample_frames(src, out, start=90, step=10.0, count=3)  # runs past the end: the last frame is held
    assert len(_luma_of_frames(out)) == 3


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
