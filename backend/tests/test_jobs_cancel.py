from __future__ import annotations

import threading
from pathlib import Path

from backend import jobs


def _store():
    return jobs.JobStore(session=None)


def test_cancel_pending_job_removes_it_and_reports_cancelled_without_running_it():
    store = _store()
    gate = threading.Event()
    ran: list[str] = []
    done: dict[str, dict] = {}

    def first(_dest: Path) -> Path:
        gate.wait(5)
        return Path("a.mp4")

    def second(_dest: Path) -> Path:
        ran.append("second")
        return Path("b.mp4")

    store.submit_callable(first, Path("a.mp4"), lambda **kw: done.__setitem__("a", kw))
    j2 = store.submit_callable(second, Path("b.mp4"), lambda **kw: done.__setitem__("b", kw))
    assert [e["status"] for e in store.snapshot()] == ["running", "queued"]
    assert store.cancel(j2) is True
    assert [e["status"] for e in store.snapshot()] == ["running"]
    assert done["b"]["status"] == "failed" and done["b"]["error"] == jobs.CANCELLED
    gate.set()
    for _ in range(100):
        if "a" in done:
            break
        threading.Event().wait(0.05)
    assert ran == [] and done["a"]["status"] == "done"


def test_cancel_running_callable_calls_its_hook_and_unknown_or_hookless_returns_false():
    store = _store()
    gate = threading.Event()
    hooked: list[int] = []

    def slow(_dest: Path) -> Path:
        gate.wait(5)
        return Path("a.mp4")

    j1 = store.submit_callable(slow, Path("a.mp4"), lambda **kw: None, on_cancel=lambda: (hooked.append(1), gate.set()))
    assert store.cancel(j1) is True and hooked == [1]
    assert store.cancel("nope") is False
    j2 = store.submit_callable(lambda _d: Path("x.mp4"), Path("x.mp4"), lambda **kw: None)
    threading.Event().wait(0.3)
    assert store.cancel(j2) is False  # already finished


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
