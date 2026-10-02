from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from backend.swap import assemble, scenes


def _make(path: Path, frames: int, color: str, audio: bool = False) -> str:
    cmd = [scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=96x160:r=24:d={frames / 24}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={frames / 24}", "-c:a", "aac", "-shortest"]
    cmd += ["-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return str(path)


def _has_audio(path: str) -> bool:
    return "Audio:" in subprocess.run([scenes.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr


def test_join_three_clips_sums_frames():
    with tempfile.TemporaryDirectory() as d:
        parts = [_make(Path(d) / f"{i}.mp4", 24, c) for i, c in enumerate(["red", "green", "blue"])]
        out = str(Path(d) / "out.mp4")
        assemble.join_videos(parts, out)
        assert scenes.count_frames(out) == 72


def test_assemble_with_audio_source_keeps_audio():
    with tempfile.TemporaryDirectory() as d:
        a = _make(Path(d) / "a.mp4", 24, "red")
        b = _make(Path(d) / "b.mp4", 24, "blue")
        src = _make(Path(d) / "src.mp4", 48, "white", audio=True)
        out = str(Path(d) / "final.mp4")
        info = assemble.assemble_project([[a], [b]], src, out)
        assert info["audio"] is True and info["frames"] == 48 and abs(info["seconds"] - 2.0) < 0.1
        assert _has_audio(out)


def test_assemble_without_audio_still_produces_video():
    with tempfile.TemporaryDirectory() as d:
        a = _make(Path(d) / "a.mp4", 24, "red")
        b = _make(Path(d) / "b.mp4", 12, "blue")
        c = _make(Path(d) / "c.mp4", 12, "green")
        src = _make(Path(d) / "src.mp4", 48, "white")
        out = str(Path(d) / "final.mp4")
        info = assemble.assemble_project([[a], [b, c]], src, out)
        assert info["audio"] is False and info["frames"] == 48
        assert not _has_audio(out) and scenes.count_frames(out) == 48


def test_join_of_mixed_sizes_keeps_every_frame_and_the_first_size():
    # Live smoke test: a 704x1248 swapped clip between 720x1280 original scenes lost 3 of 580 frames.
    with tempfile.TemporaryDirectory() as d:
        src = _make(Path(d) / "src.mp4", 300, "red")
        files = []
        for i, n in enumerate([35, 34, 69, 64, 64, 65]):
            out = str(Path(d) / f"p{i}.mp4")
            if i == 3:
                subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=94x156:r=24", "-frames:v", str(n),
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", out], check=True)
            else:
                scenes.extract_segment(src, out, 0, 299, 24.0, 0, n - 1, None)
            files.append(out)
        joined = str(Path(d) / "j.mp4")
        assemble.join_videos(files, joined, size=(96, 160))
        assert scenes.count_frames(joined) == sum([35, 34, 69, 64, 64, 65])
        import cv2
        cap = cv2.VideoCapture(joined)
        got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        cap.release()
        assert got == (96, 160)


def test_audio_shorter_than_the_picture_does_not_cut_frames():
    # Live: the original audio ran 0.17 s short and "-shortest" dropped the last 4 frames of the finished video.
    with tempfile.TemporaryDirectory() as d:
        a = _make(Path(d) / "a.mp4", 48, "red")
        src = _make(Path(d) / "src.mp4", 24, "white", audio=True)  # 1 s of picture and audio against 2 s of swapped video
        out = str(Path(d) / "final.mp4")
        info = assemble.assemble_project([[a]], src, out)
        assert info["audio"] is True and scenes.count_frames(out) == 48 and info["frames"] == 48


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
