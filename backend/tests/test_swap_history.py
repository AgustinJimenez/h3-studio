from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.swap import runner, store
from backend.tests.test_swap_api import _clip, _create, _env, _setup_project
from backend.tests.test_swap_runner import FakeClient, FakeStore, _project, _setup


def test_every_run_keeps_its_own_files_and_a_history_entry():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["_dir"] = str(d)
        proj["passes"][0]["history"] = []
        fs = FakeStore(proj)
        for seed in (1, 2):
            proj["passes"][0]["seed"] = seed
            r = runner.make_runner("p1", "pass0000aaaa", store_mod=fs, client_factory=lambda: FakeClient(out), release_wangp=lambda: None)
            r(d / "x.mp4")
        hist = proj["passes"][0]["history"]
        assert [h["seed"] for h in hist] == [1, 2] and len({h["output_path"] for h in hist}) == 2
        assert all(Path(h["output_path"]).exists() and Path(h["raw_path"]).exists() for h in hist)
        assert hist[0]["quality"] == "final" and hist[0]["width"] == 96 or hist[0]["width"] > 0
        assert proj["passes"][0]["output_path"] == hist[1]["output_path"]  # the newest run is the active one
        assert hist[0]["extra_loras"] == []


def _two_runs(tc, pid):
    """Plan, then give scene 1's pass two finished runs through the store (as the runner would)."""
    base = store.project_dir(store.find(pid))
    p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
    runs = []
    for i, seed in enumerate((11, 22)):
        out = _clip(base / "passes" / f"{p['id']}_r{i}.mp4", 24)
        raw = _clip(base / "passes" / f"{p['id']}_r{i}_raw.mp4", 39)
        runs.append({"id": f"r{i}", "created_at": 100.0 + i, "quality": "final", "width": 320, "height": 320, "seed": seed,
                     "seconds": 60.0, "mean_luma": 80.0, "output_path": out, "raw_path": raw, "prompt": "P"})
    store.update_pass(pid, p["id"], history=runs, status="done", output_path=runs[1]["output_path"], raw_path=runs[1]["raw_path"], seed=22)
    return p["id"], runs


def test_view_lists_history_with_urls_and_marks_the_active_run():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        pass_id, runs = _two_runs(tc, pid)
        v = [p for p in tc.get(f"/swaps/{pid}").json()["passes"] if p["id"] == pass_id][0]
        assert [h["seed"] for h in v["history"]] == [11, 22]
        assert all(h["output_url"].startswith("/swap-media/") for h in v["history"])
        assert [h["active"] for h in v["history"]] == [False, True]


def test_use_run_makes_an_older_run_the_active_result():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        pass_id, runs = _two_runs(tc, pid)
        r = tc.post(f"/swaps/{pid}/passes/{pass_id}/use-run", json={"run_id": "r0"})
        assert r.status_code == 200, r.text
        v = [p for p in r.json()["passes"] if p["id"] == pass_id][0]
        assert v["output_path"] == runs[0]["output_path"] and v["params"]["seed"] == 11 and v["params"]["width"] == 320
        assert tc.post(f"/swaps/{pid}/passes/{pass_id}/use-run", json={"run_id": "nope"}).status_code == 404


def test_delete_run_removes_files_but_not_the_active_run():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        pass_id, runs = _two_runs(tc, pid)
        assert tc.delete(f"/swaps/{pid}/passes/{pass_id}/runs/r1").status_code == 409
        r = tc.delete(f"/swaps/{pid}/passes/{pass_id}/runs/r0")
        assert r.status_code == 200
        assert not Path(runs[0]["output_path"]).exists() and Path(runs[1]["output_path"]).exists()
        v = [p for p in r.json()["passes"] if p["id"] == pass_id][0]
        assert [h["id"] for h in v["history"]] == ["r1"]


def test_replanning_a_scene_keeps_its_history():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        pass_id, runs = _two_runs(tc, pid)
        store.update_pass(pid, pass_id, status="done")
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        again = [p for p in store.find(pid)["passes"] if p["scene_index"] == 0][0]
        assert [h["seed"] for h in again["history"]] == [11, 22]
        # and a full re-plan does too
        for p in store.find(pid)["passes"]:
            store.update_pass(pid, p["id"], status="draft")
        full = tc.post(f"/swaps/{pid}/plan").json()
        assert [h["seed"] for h in [p for p in full["passes"] if p["scene_index"] == 0][0]["history"]] == [11, 22]


def test_existing_finished_pass_without_history_gets_one_entry():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        out = _clip(store.project_dir(store.find(pid)) / "passes" / "old.mp4", 24)
        store.update_pass(pid, p["id"], status="done", output_path=out, raw_path=out, seconds=5.0, quality="final")
        v = [x for x in tc.get(f"/swaps/{pid}").json()["passes"] if x["id"] == p["id"]][0]
        assert len(v["history"]) == 1 and v["history"][0]["active"] is True and v["history"][0]["output_url"]


def test_rerunning_a_pass_that_finished_before_history_keeps_that_result_in_the_list():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        out = _clip(store.project_dir(store.find(pid)) / "passes" / "old.mp4", 24)
        store.update_pass(pid, p["id"], status="done", output_path=out, raw_path=out, seconds=5.0, quality="final", seed=33)
        tc.post(f"/swaps/{pid}/passes/{p['id']}/rerun", json={"seed": 5})
        v = [x for x in tc.get(f"/swaps/{pid}").json()["passes"] if x["id"] == p["id"]][0]
        assert [h["output_path"] for h in store.find(pid)["passes"][0]["history"]] == [out]
        assert v["status"] in ("queued", "running") and len(v["history"]) == 1 and v["history"][0]["seed"] == 33


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
