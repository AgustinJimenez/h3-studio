from __future__ import annotations

from backend import clip_history


def test_an_entry_keeps_what_is_needed_to_compare_and_restore_a_run():
    e = clip_history.make_entry("a/c1_x.mp4", {"seed": 5, "resolution": "1088x1920", "num_inference_steps": 20, "prompt": "p"}, 3000.5, 100.0)
    assert e["output_path"] == "a/c1_x.mp4" and e["seed"] == 5 and e["resolution"] == "1088x1920" and e["steps"] == 20
    assert e["seconds"] == 3000.5 and e["finished_at"] == 100.0 and e["id"] and e["settings"]["prompt"] == "p"


def test_runs_are_listed_oldest_first_and_the_same_file_is_not_added_twice():
    h = clip_history.add([], clip_history.make_entry("a.mp4", {}, 1, 1.0))
    h = clip_history.add(h, clip_history.make_entry("b.mp4", {}, 1, 2.0))
    h = clip_history.add(h, clip_history.make_entry("a.mp4", {}, 1, 3.0))
    assert [e["output_path"] for e in h] == ["a.mp4", "b.mp4"]


def test_find_returns_the_entry_by_id_or_none():
    e = clip_history.make_entry("a.mp4", {}, 1, 1.0)
    assert clip_history.find([e], e["id"]) is e and clip_history.find([e], "nope") is None


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
