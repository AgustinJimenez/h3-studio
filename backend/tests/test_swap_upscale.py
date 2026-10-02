from __future__ import annotations

import tempfile
from pathlib import Path

from backend.swap import scenes, upscale
from backend.tests.test_swap_runner import FakeStore, _make, _project


def _setup(d: Path):
    src = _make(d / "src.mp4", 48, "white")
    proj = _project(d, src, frames=12)
    proj["_dir"] = str(d)
    out = _make(d / "result.mp4", 12, "gray")
    proj["passes"][0].update(status="done", output_path=out, raw_path=out, history=[
        {"id": "r1", "created_at": 1.0, "quality": "final", "width": 96, "height": 160, "seed": 1, "output_path": out, "raw_path": out}])
    return proj, out


def test_upscale_adds_a_history_entry_and_keeps_the_active_result():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        proj, out = _setup(d)
        submitted: list[dict] = []

        class Jobs:
            def submit(self, settings, dest, on_done, on_queued=None, on_running=None):
                submitted.append(settings)
                if on_queued:
                    on_queued("jobU")
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                _make(Path(dest), 12, "red", size="192x320")  # what WanGP leaves at dest: twice the size
                on_done(status="done", output_path=str(dest), error=None, duration_seconds=3)
                return "jobU"

        upscale.start("p1", "pass0000aaaa", store_mod=FakeStore(proj), job_store=Jobs(), process_id="flashvsr", multiplier=2.0,
                      build_settings=lambda media, process_id, multiplier: {"video_source": media, "spatial_upsampling": f"{process_id}{multiplier}"})
        assert submitted[0]["video_source"] == out and submitted[0]["spatial_upsampling"] == "flashvsr2.0"
        p = proj["passes"][0]
        assert p["status"] == "done" and p["output_path"] == out  # the result in use is unchanged
        assert len(p["history"]) == 2
        new = p["history"][-1]
        assert new["method"] == "upscale" and new["process"] == "flashvsr" and new["width"] == 192 and new["height"] == 320
        assert scenes.count_frames(new["output_path"]) == 12 and new["raw_path"] == out


def test_a_failed_upscale_restores_the_pass_and_records_the_error():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        proj, out = _setup(d)

        class Jobs:
            def submit(self, settings, dest, on_done, on_queued=None, on_running=None):
                on_done(status="failed", output_path=None, error="out of memory", duration_seconds=1)

        upscale.start("p1", "pass0000aaaa", store_mod=FakeStore(proj), job_store=Jobs(), process_id="seedvr2", multiplier=2.0,
                      build_settings=lambda media, process_id, multiplier: {"video_source": media})
        p = proj["passes"][0]
        assert p["status"] == "done" and p["output_path"] == out and len(p["history"]) == 1
        assert "out of memory" in (p.get("upscale_error") or "")


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
