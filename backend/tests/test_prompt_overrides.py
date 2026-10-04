from __future__ import annotations

from backend import prompt

SING = {"model_type": "minimax_h3_singularity_ref2va", "model_filename": "sing.safetensors", "resolution": "1088x1920", "num_inference_steps": 20}


def _video() -> dict:
    return {"id": "v1", "title": "t", "characters": [], "template_settings": dict(SING), "base_prompt": {}}


def _clip(**kw) -> dict:
    return {"id": "c1", "order": 0, "shot_prompt": "A man walks.", "seed": 5, "video_length": 124, **kw}


def test_a_clip_without_overrides_uses_the_template():
    s = prompt.build_generation_settings(_video(), _clip())
    assert (s["resolution"], s["num_inference_steps"], s["model_type"]) == ("1088x1920", 20, "minimax_h3_singularity_ref2va")


def test_a_clip_resolution_replaces_the_template_resolution_for_that_clip_only():
    v = _video()
    s = prompt.build_generation_settings(v, _clip(resolution_override="576x1024"))
    assert s["resolution"] == "576x1024" and v["template_settings"]["resolution"] == "1088x1920"


def test_the_fast_model_preset_switches_model_file_and_steps():
    s = prompt.build_generation_settings(_video(), _clip(model_preset="pdd8"))
    assert s["model_type"] == "minimax_h3_ref2va_pruned_pdd" and s["num_inference_steps"] == 8
    assert s["model_filename"] == prompt.MODEL_PRESETS["pdd8"]["model_filename"]


def test_an_unknown_preset_or_empty_override_is_ignored():
    s = prompt.build_generation_settings(_video(), _clip(model_preset="", resolution_override=""))
    assert s["model_type"] == "minimax_h3_singularity_ref2va" and s["resolution"] == "1088x1920"


def test_two_phase_runs_the_h3_latent_upscaler_between_a_draft_and_the_refinement():
    s = prompt.build_generation_settings(_video(), _clip(two_phase=True))
    assert s["guidance_phases"] == 2 and s["switch_threshold"] == 0.9035 and s["resolution"] == "1088x1920"


def test_two_phase_off_keeps_a_single_phase():
    s = prompt.build_generation_settings(_video(), _clip(two_phase=False))
    assert s["guidance_phases"] == 1 and "switch_threshold" not in s


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
