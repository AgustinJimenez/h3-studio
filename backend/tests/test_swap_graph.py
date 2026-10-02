from __future__ import annotations

from backend.swap import graph

ARGS = dict(video_name="src.mp4", image_name="face.png", prompt="P", width=704, height=1248, length=73, seed=904234,
            prefix="h3studio/swap_test")


def test_final_graph_is_twenty_steps_res_multistep_without_turbo_or_audio():
    g = graph.build_graph(quality="final", **ARGS)
    assert "3b" not in g
    assert g["14"]["inputs"]["sampler_name"] == "res_multistep"
    assert g["15"]["inputs"] == {"model": ["1", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}
    assert g["16"]["inputs"]["model"] == ["3", 0]
    assert "audio" not in g["20"]["inputs"] and g["20"]["inputs"]["fps"] == 24
    assert g["21"]["class_type"] == "SaveVideo" and graph.SAVE_NODE == "21"
    assert g["21"]["inputs"]["filename_prefix"] == "h3studio/swap_test"


def test_swap_lora_and_model_files():
    g = graph.build_graph(quality="final", **ARGS)
    assert g["1"]["inputs"]["unet_name"] == "minimax_h3_ref2va_pruned_fp8_scaled.safetensors"
    assert g["3"]["inputs"]["lora_name"] == "h3_character_swap_pro4500_1000.safetensors" and g["3"]["inputs"]["strength_model"] == 1.0
    assert g["2"]["inputs"]["type"] == "minimax"


def test_reference_inputs_are_zero_based_and_length_is_the_padded_one():
    g = graph.build_graph(quality="final", **ARGS)
    ref = g["12"]["inputs"]
    assert ref["ref_images.ref_image_0"] == ["img0", 0] and ref["ref_videos.ref_video_0"] == ["10", 0]
    assert ref["length"] == 73 and ref["width"] == 704 and ref["height"] == 1248 and ref["prompt"] == "P"
    assert g["img0"]["inputs"]["image"] == "face.png" and g["9"]["inputs"]["file"] == "src.mp4"
    assert g["13"]["inputs"]["noise_seed"] == 904234


def test_preview_stacks_turbo_at_point_six_with_four_steps_and_euler():
    g = graph.build_graph(quality="preview", **ARGS)
    assert g["3b"]["class_type"] == "LoraLoaderModelOnly" and g["3b"]["inputs"]["model"] == ["3", 0]
    assert g["3b"]["inputs"]["lora_name"] == "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
    assert g["3b"]["inputs"]["strength_model"] == 0.6
    assert g["16"]["inputs"]["model"] == ["3b", 0]
    assert g["14"]["inputs"]["sampler_name"] == "euler" and g["15"]["inputs"]["steps"] == 4


def test_unknown_quality_raises():
    try:
        graph.build_graph(quality="ultra", **ARGS)
    except ValueError as exc:
        assert "ultra" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_quality_table_has_the_chunk_maxima():
    assert graph.QUALITY["final"]["chunk_max"] == 243 and graph.QUALITY["preview"]["chunk_max"] == 124


def test_decode_is_tiled_so_it_fits_next_to_other_gpu_users():
    # Live: a plain VAEDecode stalled for hours at 100% GPU whenever a browser held a little GPU memory.
    g = graph.build_graph(quality="final", **ARGS)
    assert g["18"]["class_type"] == "VAEDecodeTiled"
    assert g["18"]["inputs"]["tile_size"] == 512 and g["18"]["inputs"]["temporal_size"] == 64
    assert g["18"]["inputs"]["samples"] == ["17", 0] and g["18"]["inputs"]["vae"] == ["4", 0]


def test_accel8_quality_uses_the_8_step_lora_at_full_strength():
    g = graph.build_graph(quality="accel8", **ARGS)
    assert g["3b"]["inputs"]["lora_name"] == "MiniMax-H3-Ref2VA-Acc-8Step_pruned_comfy.safetensors" and g["3b"]["inputs"]["strength_model"] == 1.0
    assert g["3b"]["inputs"]["model"] == ["3", 0] and g["16"]["inputs"]["model"] == ["3b", 0]
    assert g["15"]["inputs"]["steps"] == 8 and g["14"]["inputs"]["sampler_name"] == "euler"


def test_extra_loras_are_chained_after_the_swap_lora_in_order():
    g = graph.build_graph(quality="final", extra_loras=[("ref_a.safetensors", 0.8), ("ref_b.safetensors", 1.0)], **ARGS)
    assert g["3x0"]["inputs"] == {"model": ["3", 0], "lora_name": "ref_a.safetensors", "strength_model": 0.8}
    assert g["3x1"]["inputs"]["model"] == ["3x0", 0] and g["16"]["inputs"]["model"] == ["3x1", 0]
    pre = graph.build_graph(quality="preview", extra_loras=[("ref_a.safetensors", 0.8)], **ARGS)
    assert pre["3x0"]["inputs"]["model"] == ["3b", 0] and pre["16"]["inputs"]["model"] == ["3x0", 0]


def test_control_patch_is_applied_after_the_loras_and_feeds_the_guider():
    g = graph.build_graph(quality="final", extra_loras=[("x.safetensors", 1.0)],
                          control={"patch": "p.safetensors", "strength": 0.5, "video": "edges.mp4"}, **ARGS)
    assert g["cn_l"] == {"class_type": "ModelPatchLoader", "inputs": {"name": "p.safetensors"}}
    assert g["cn_v"]["inputs"]["file"] == "edges.mp4" and g["cn_c"]["inputs"]["video"] == ["cn_v", 0]
    cn = g["cn"]
    assert cn["class_type"] == "MiniMaxH3FunControlNetApply"
    assert cn["inputs"] == {"model": ["3x0", 0], "model_patch": ["cn_l", 0], "vae": ["4", 0], "strength": 0.5,
                            "start_percent": 0.0, "end_percent": 1.0, "control_video": ["cn_c", 0]}
    assert g["16"]["inputs"]["model"] == ["cn", 0]
    assert "cn" not in graph.build_graph(quality="final", **ARGS)


def test_guide_mode_feeds_the_source_through_add_guide_and_uses_its_own_lora():
    # Head Swap / LMS LoRAs: the aligned source video goes through MiniMaxH3AddGuide at frame 0, not through the ref-video channel.
    g = graph.build_graph(quality="final", mode="guide", base_lora="minimax_h3_head_swap_v1.0_r32.safetensors", **ARGS)
    assert "ref_videos.ref_video_0" not in g["12"]["inputs"] and g["12"]["inputs"]["ref_images.ref_image_0"] == ["img0", 0]
    assert g["3"]["inputs"]["lora_name"] == "minimax_h3_head_swap_v1.0_r32.safetensors"
    ag = g["ag"]
    assert ag["class_type"] == "MiniMaxH3AddGuide" and ag["inputs"] == {
        "positive": ["12", 0], "vae": ["4", 0], "latent": ["12", 1], "image": ["10", 0], "frame_idx": 0}
    assert g["16"]["inputs"]["conditioning"] == ["ag", 0] and g["17"]["inputs"]["latent_image"] == ["12", 1]


def test_reference_image_size_can_be_max_for_identity():
    assert graph.build_graph(quality="final", **ARGS)["12"]["inputs"]["ref_image_size"] == "match"
    assert graph.build_graph(quality="final", ref_image_size="max", **ARGS)["12"]["inputs"]["ref_image_size"] == "max"


def test_guide_mode_can_run_without_a_reference_image():
    g = graph.build_graph(quality="final", mode="guide", base_lora="x.safetensors", use_ref_image=False, **ARGS)
    assert "ref_images.ref_image_0" not in g["12"]["inputs"] and "img0" not in g


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
