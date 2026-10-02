from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from backend.swap import scenes, viggle


def test_settings_use_the_viggle_model_with_the_control_video_and_the_edited_frame():
    s = viggle.build_settings("clip.mp4", "frame.png", 640, 640, seed=7, output_name="o")
    assert s["model_type"] == "viggle_animate" and s["video_prompt_type"] == "IVU"
    assert s["video_guide"] == "clip.mp4" and s["image_refs"] == ["frame.png"] and s["resolution"] == "640x640"
    assert s["seed"] == 7 and s["video_length"] == 124 and s["output_filename"] == "o" and s["prompt"].strip()  # WanGP rejects an empty one; the model ignores it


def test_first_frame_is_saved_as_png_at_the_clips_size():
    with tempfile.TemporaryDirectory() as d:
        clip = str(Path(d) / "c.mp4")
        frames = [np.full((96, 128, 3), v, np.uint8) for v in (200, 100)]
        import subprocess
        enc = subprocess.Popen([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "128x96", "-r", "24",
                                "-i", "-", "-pix_fmt", "yuv420p", clip], stdin=subprocess.PIPE)
        for f in frames:
            enc.stdin.write(f.tobytes())
        enc.stdin.close()
        enc.wait()
        out = str(Path(d) / "f.png")
        viggle.first_frame(clip, out)
        img = cv2.imread(out)
        assert img.shape[:2] == (96, 128) and abs(int(img.mean()) - 200) < 12


def test_edit_prompt_names_both_pictures_and_keeps_the_pose():
    cast = {"name": "Lafi", "appearance": "a young woman", "outfit": "a pink t-shirt"}
    text = viggle.edit_prompt("the woman looking up", cast)
    assert "image 1" in text.lower() and "image 2" in text.lower() and "pose" in text.lower() and "pink t-shirt" in text


def test_start_runs_prepare_then_viggle_and_records_the_result_in_the_pass_history():
    from backend.tests.test_swap_runner import FakeStore, _make, _project

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _make(d / "src.mp4", 96, "white")
        proj = _project(d, src, frames=48)
        proj["_dir"] = str(d)
        proj["source"].update(width=96, height=160)
        proj["passes"][0]["history"] = []
        frame = d / "edited.png"
        cv2.imencode(".png", np.full((160, 96, 3), 120, np.uint8))[1].tofile(str(frame))
        submitted: list[dict] = []

        class Jobs:
            def submit_callable(self, runner_fn, dest, on_done, on_queued=None, on_running=None, on_cancel=None):
                if on_queued:
                    on_queued("jobA")
                try:
                    out = runner_fn(dest)
                    on_done(status="done", output_path=str(out), error=None, duration_seconds=1)
                except Exception as exc:  # noqa: BLE001
                    on_done(status="failed", output_path=None, error=str(exc), duration_seconds=1)
                return "jobA"

            def submit(self, settings, dest, on_done, on_queued=None, on_running=None):
                submitted.append(settings)
                if on_queued:
                    on_queued("jobB")
                _make(Path(dest), 124, "gray")  # what WanGP would leave at dest
                on_done(status="done", output_path=str(dest), error=None, duration_seconds=2)
                return "jobB"

        viggle.start("p1", "pass0000aaaa", store_mod=FakeStore(proj), job_store=Jobs(), release_wangp=lambda: None, size=96,
                     seed=5, frame_path=str(frame))
        assert len(submitted) == 1 and submitted[0]["model_type"] == "viggle_animate" and submitted[0]["seed"] == 5
        assert Path(submitted[0]["video_guide"]).exists() and scenes.count_frames(submitted[0]["video_guide"]) == 124
        p = proj["passes"][0]
        assert p["status"] == "done" and p["method"] == "viggle" and len(p["history"]) == 1
        assert scenes.count_frames(p["output_path"]) == 48 and p["raw_frames"] == 124
        assert p["history"][0]["method"] == "viggle" and Path(p["history"][0]["edited_frame"]).exists()


def test_the_expression_comes_first_in_the_edit_prompt_when_given():
    cast = {"name": "Lafi", "appearance": "a young woman", "outfit": "a pink t-shirt"}
    text = viggle.edit_prompt("the woman", cast, expression="Her mouth is wide open and she looks up.")
    assert text.startswith("Her mouth is wide open and she looks up.") and "exactly" in text.split("Image 1")[0].lower()
    assert not viggle.edit_prompt("the woman", cast).startswith("Her")


def test_a_supplied_clip_is_used_as_is_and_the_result_is_sliced_for_the_pass():
    from backend.tests.test_swap_runner import FakeStore, _make, _project

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _make(d / "src.mp4", 96, "white")
        proj = _project(d, src, frames=20)
        proj["_dir"] = str(d)
        proj["source"].update(width=96, height=160)
        proj["passes"][0]["history"] = []
        mine = _make(d / "joined.mp4", 124, "red")
        frame = d / "edited.png"
        cv2.imencode(".png", np.full((160, 96, 3), 120, np.uint8))[1].tofile(str(frame))
        submitted: list[dict] = []

        class Jobs:
            def submit_callable(self, runner_fn, dest, on_done, on_queued=None, on_running=None, on_cancel=None):
                out = runner_fn(dest)
                on_done(status="done", output_path=str(out), error=None, duration_seconds=1)

            def submit(self, settings, dest, on_done, on_queued=None, on_running=None):
                submitted.append(settings)
                _make(Path(dest), 124, "gray")
                on_done(status="done", output_path=str(dest), error=None, duration_seconds=2)

        viggle.start("p1", "pass0000aaaa", store_mod=FakeStore(proj), job_store=Jobs(), release_wangp=lambda: None, size=96, seed=1,
                     frame_path=str(frame), clip_path=mine, slice_start=57)
        assert scenes.count_frames(submitted[0]["video_guide"]) == 124 and submitted[0]["video_guide"] != mine  # a copy beside the pass files
        p = proj["passes"][0]
        assert p["status"] == "done" and scenes.count_frames(p["output_path"]) == 20
        assert p["raw_frames"] == 124 - 57 and p["lead_used"] == 57  # frames available from the scene's start, and what precedes it


def test_a_slowed_down_clip_is_sampled_back_to_the_scenes_real_length():
    from backend.tests.test_swap_runner import FakeStore, _make, _project

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src = _make(d / "src.mp4", 96, "white")
        proj = _project(d, src, frames=11)
        proj["_dir"] = str(d)
        proj["source"].update(width=96, height=160)
        proj["passes"][0]["history"] = []
        slow = _make(d / "slow.mp4", 124, "red")
        frame = d / "edited.png"
        cv2.imencode(".png", np.full((160, 96, 3), 120, np.uint8))[1].tofile(str(frame))

        class Jobs:
            def submit_callable(self, runner_fn, dest, on_done, on_queued=None, on_running=None, on_cancel=None):
                on_done(status="done", output_path=str(runner_fn(dest)), error=None, duration_seconds=1)

            def submit(self, settings, dest, on_done, on_queued=None, on_running=None):
                _make(Path(dest), 124, "gray")
                on_done(status="done", output_path=str(dest), error=None, duration_seconds=2)

        viggle.start("p1", "pass0000aaaa", store_mod=FakeStore(proj), job_store=Jobs(), release_wangp=lambda: None, size=96, seed=1,
                     frame_path=str(frame), clip_path=slow, sample_step=12.5)
        p = proj["passes"][0]
        assert p["status"] == "done" and scenes.count_frames(p["output_path"]) == 11  # the scene's own 11 frames, not 11 of the 124


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
