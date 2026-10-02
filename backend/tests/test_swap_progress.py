from __future__ import annotations

import tempfile
from pathlib import Path

from backend.swap import progress, runner
from backend.tests.test_swap_runner import FakeClient, FakeStore, _project, _setup


def test_progress_message_parser_maps_sampling_steps_and_stages():
    p = progress.from_message({"type": "progress", "data": {"value": 5, "max": 20, "prompt_id": "x", "node": "17"}}, "x")
    assert p == {"stage": "Sampling", "value": 5, "max": 20, "fraction": 0.25}
    s = progress.from_message({"type": "executing", "data": {"node": "18", "prompt_id": "x"}}, "x")
    assert s == {"stage": "Decoding video", "value": None, "max": None, "fraction": None}
    assert progress.from_message({"type": "progress", "data": {"value": 1, "max": 4, "prompt_id": "other", "node": "17"}}, "x") is None
    assert progress.from_message({"type": "status", "data": {}}, "x") is None
    assert progress.from_message({"type": "executing", "data": {"node": None, "prompt_id": "x"}}, "x") is None


def test_registry_set_get_clear():
    progress.set("pass1", {"stage": "Sampling", "value": 1, "max": 4, "fraction": 0.25})
    assert progress.get("pass1")["fraction"] == 0.25
    progress.clear("pass1")
    assert progress.get("pass1") is None


def test_runner_publishes_progress_while_running_and_clears_it_after():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["_dir"] = str(d)
        seen: list[str] = []

        class Reporting(FakeClient):
            def wait(self, prompt_id):
                self.on_progress({"stage": "Sampling", "value": 2, "max": 4, "fraction": 0.5})
                seen.append(progress.get("pass0000aaaa")["stage"])
                return super().wait(prompt_id)

        client = Reporting(out)
        r = runner.make_runner("p1", "pass0000aaaa", store_mod=FakeStore(proj), client_factory=lambda: client, release_wangp=lambda: None)
        r(d / "x.mp4")
        assert seen == ["Sampling"] and progress.get("pass0000aaaa") is None


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
