from __future__ import annotations

import tempfile
from pathlib import Path

from backend.swap import scenes, store

SRC = {"path": "x.mp4", "width": 704, "height": 1248, "fps": 30.0, "frames": 300, "duration": 10.0, "has_audio": True}


def _with_root(fn):
    def wrapper():
        with tempfile.TemporaryDirectory() as d:
            old = store.ROOT
            store.ROOT = Path(d)
            try:
                fn()
            finally:
                store.ROOT = old
    wrapper.__name__ = fn.__name__
    return wrapper


def _cast(outfit_b: str = "a blue coat"):
    return [{"id": "c1", "name": "A", "image_path": "a.png", "appearance": "a tall man", "outfit": "a red coat", "body": ""},
            {"id": "c2", "name": "B", "image_path": "b.png", "appearance": "a short man", "outfit": outfit_b, "body": ""}]


def _people():
    return [{"id": "pa", "cast_id": "c1", "target_description": "the man on the left", "order": 0},
            {"id": "pb", "cast_id": "c2", "target_description": "the man on the right", "order": 1}]


@_with_root
def test_round_trip_and_folder_layout():
    p = store.new_project("My Clip", SRC)
    assert p["status"] == "draft" and p["settings"]["chunk_max_final"] == 243 and p["settings"]["chunk_max_preview"] == 124
    base = store.project_dir(p)
    assert all((base / sub).is_dir() for sub in ("source", "passes", "final", "thumbs"))
    assert store.find(p["id"])["title"] == "My Clip"
    assert [x["id"] for x in store.load_all()] == [p["id"]]


@_with_root
def test_update_applies_sequential_changes():
    p = store.new_project("t", SRC)
    store.update(p["id"], lambda pr: pr.update(title="one"))
    store.update(p["id"], lambda pr: pr["plan_notes"].append("two"))
    got = store.find(p["id"])
    assert got["title"] == "one" and got["plan_notes"] == ["two"]


@_with_root
def test_delete_removes_folder_and_find_raises():
    p = store.new_project("t", SRC)
    base = store.project_dir(p)
    store.delete(p["id"])
    assert not base.exists()
    try:
        store.find(p["id"])
    except store.NotFound:
        pass
    else:
        raise AssertionError("expected NotFound")


@_with_root
def test_build_plan_orders_passes_and_skips_empty_scenes():
    p = store.new_project("t", SRC)
    built = scenes.build_scenes([100, 200], 300, 30.0, 10)  # 3 scenes of ~80 frames, chunked by 10 -> several chunks
    store.update(p["id"], lambda pr: pr.update(cast=_cast()))
    store.update(p["id"], lambda pr: store.set_scenes(pr, built))

    def assign(pr):
        pr["scenes"][0]["people"] = _people()
        pr["scenes"][1]["people"] = []
        pr["scenes"][2]["people"] = _people()[:1]
        pr["scenes"][2]["chunks"] = pr["scenes"][2]["chunks"][:2]
    store.update(p["id"], assign)
    plan = store.build_plan(store.find(p["id"]))
    store.save(plan)
    passes = store.find(p["id"])["passes"]
    s0 = [x for x in passes if x["scene_index"] == 0]
    n_chunks0 = len(built[0]["chunks"])
    assert len(s0) == 2 * n_chunks0
    assert [(x["chunk_index"], x["order"]) for x in s0[:2]] == [(0, 0), (0, 1)]
    assert all(x["status"] == "draft" and x["job_id"] is None and x["quality"] == "final" for x in passes)
    assert not [x for x in passes if x["scene_index"] == 1]
    assert len([x for x in passes if x["scene_index"] == 2]) == 2
    assert any("Scene 2" in n for n in plan["plan_notes"])
    assert "red coat" in s0[0]["prompt"] and "the man on the left" in s0[0]["prompt"]


@_with_root
def test_empty_outfit_blocks_only_that_pass():
    p = store.new_project("t", SRC)
    built = scenes.build_scenes([], 60, 30.0, 243)
    store.update(p["id"], lambda pr: (pr.update(cast=_cast(outfit_b="")), store.set_scenes(pr, built)))
    store.update(p["id"], lambda pr: pr["scenes"][0].update(people=_people()))
    plan = store.build_plan(store.find(p["id"]))
    by_order = {x["order"]: x for x in plan["passes"]}
    assert by_order[0]["status"] == "draft"
    assert by_order[1]["status"] == "blocked" and "outfit" in by_order[1]["error"]


@_with_root
def test_update_pass_changes_only_that_pass():
    p = store.new_project("t", SRC)
    built = scenes.build_scenes([], 60, 30.0, 243)
    store.update(p["id"], lambda pr: (pr.update(cast=_cast()), store.set_scenes(pr, built)))
    store.update(p["id"], lambda pr: pr["scenes"][0].update(people=_people()))
    store.save(store.build_plan(store.find(p["id"])))
    a, b = store.find(p["id"])["passes"]
    store.update_pass(p["id"], a["id"], status="queued", job_id="j1")
    got = store.find(p["id"])["passes"]
    assert got[0]["status"] == "queued" and got[0]["job_id"] == "j1" and got[1]["status"] == "draft"


@_with_root
def test_rechunk_follows_quality_and_default_size_is_grid_aligned():
    p = store.new_project("t", SRC)
    built = scenes.build_scenes([], 300, 30.0, 243)  # 240 frames at 24 fps
    store.update(p["id"], lambda pr: store.set_scenes(pr, built))
    pr = store.find(p["id"])
    assert len(pr["scenes"][0]["chunks"]) == 1
    pr["settings"]["quality"] = "preview"
    store.rechunk(pr)
    ch = pr["scenes"][0]["chunks"]
    assert len(ch) == 2 and sum(c["frames_24"] for c in ch) == 240 and all(c["padded_frames"] % 17 == 5 for c in ch)
    w, h = store.default_size(720, 1280)
    assert (w, h) == (704, 1248)
    w, h = store.default_size(1920, 1080)
    assert w % 32 == 0 and h % 32 == 0 and w > h


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
