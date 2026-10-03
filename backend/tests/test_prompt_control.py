from __future__ import annotations

from backend import prompt


def _video() -> dict:
    return {"id": "v1", "title": "t", "characters": [], "template_settings": {}, "base_prompt": {}}


def _clip(**kw) -> dict:
    return {"id": "c1", "order": 0, "shot_prompt": "A man walks.", "seed": 5, "video_length": 124, "control_video_path": "E:/previs/shot.mp4", **kw}


def test_a_control_video_is_used_by_default():
    s = prompt.build_generation_settings(_video(), _clip())
    assert s["video_guide"] == "E:/previs/shot.mp4" and "DV" in s["video_prompt_type"]
    assert prompt.CONTROL_VIDEO_DEFINITION in s["prompt"]


def test_a_disabled_control_video_stays_attached_but_is_left_out_of_the_generation():
    s = prompt.build_generation_settings(_video(), _clip(control_video_enabled=False))
    assert "video_guide" not in s and "DV" not in (s.get("video_prompt_type") or "")
    assert prompt.CONTROL_VIDEO_DEFINITION not in s["prompt"] and prompt.CONTROL_VIDEO_RETENTION not in s["prompt"]


def test_enabled_true_is_the_same_as_the_default():
    a = prompt.build_generation_settings(_video(), _clip())
    b = prompt.build_generation_settings(_video(), _clip(control_video_enabled=True))
    assert a == b


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
