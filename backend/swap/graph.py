"""ComfyUI API graph for one swap pass (MiniMax H3 ref2va + the character-swap LoRA).

Ported from the graph verified by hand (see AGENTS.md "Character swap on an existing video").
Final = 20 steps res_multistep/simple. Preview = turbo LoRA at 0.6, 4 steps, euler/simple.
"""

from __future__ import annotations

from typing import Any

SAVE_NODE = "21"
FPS = 24

UNET = "minimax_h3_ref2va_pruned_fp8_scaled.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
SWAP_LORA = "h3_character_swap_pro4500_1000.safetensors"
TURBO_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
CONTROL_PATCH = "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"  # Kijai/MiniMax-H3-experimental/model_patches
ACCEL8_LORA = "MiniMax-H3-Ref2VA-Acc-8Step_pruned_comfy.safetensors"  # Kijai/MiniMax-H3-experimental

# chunk_max: longest chunk rendered in one go (a 260-frame turbo run produced black video, so preview stays at 124)
QUALITY: dict[str, dict[str, Any]] = {
    "final": {"steps": 20, "sampler": "res_multistep", "lora": None, "chunk_max": 243},
    "preview": {"steps": 4, "sampler": "euler", "lora": (TURBO_LORA, 0.6), "chunk_max": 124},
    "accel8": {"steps": 8, "sampler": "euler", "lora": (ACCEL8_LORA, 1.0), "chunk_max": 243},  # experimental
}


def lora_chain(quality: str, extra_loras: list[tuple[str, float]] | None = None) -> list[tuple[str, float]]:
    """Every LoRA a pass uses, in the order they are applied (the swap LoRA first)."""
    q = QUALITY[quality]
    return [(SWAP_LORA, 1.0)] + ([q["lora"]] if q["lora"] else []) + list(extra_loras or [])


def build_graph(*, video_name: str, image_name: str, prompt: str, width: int, height: int, length: int, seed: int,
                quality: str, prefix: str, extra_loras: list[tuple[str, float]] | None = None,
                control: dict[str, Any] | None = None, mode: str = "ref_video", base_lora: str = SWAP_LORA,
                use_ref_image: bool = True, ref_image_size: str = "match") -> dict[str, Any]:
    if quality not in QUALITY:
        raise ValueError(f"unknown quality {quality!r}")
    q = QUALITY[quality]
    g: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}},
        "9": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "10": {"class_type": "GetVideoComponents", "inputs": {"video": ["9", 0]}},
        "3": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": base_lora, "strength_model": 1.0}},
        "img0": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "12": {"class_type": "MiniMaxH3ReferenceToVideo",
               "inputs": {"clip": ["2", 0], "vae": ["4", 0], "audio_vae": ["5", 0], "prompt": prompt,
                          "width": width, "height": height, "length": length,
                          "ref_image_size": ref_image_size,
                          "ref_images.ref_image_0": ["img0", 0], "ref_videos.ref_video_0": ["10", 0]}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": q["sampler"]}},
        "15": {"class_type": "BasicScheduler",
               "inputs": {"model": ["1", 0], "scheduler": "simple", "steps": q["steps"], "denoise": 1.0}},
        "16": {"class_type": "BasicGuider", "inputs": {"model": ["3", 0], "conditioning": ["12", 0]}},
        "17": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["13", 0], "guider": ["16", 0], "sampler": ["14", 0], "sigmas": ["15", 0],
                          "latent_image": ["12", 1]}},
        # Tiled: the plain decode needs the last GB of VRAM and stalls (100% GPU, hours) when anything else, even a
        # browser page, holds a little GPU memory.
        "18": {"class_type": "VAEDecodeTiled",
               "inputs": {"samples": ["17", 0], "vae": ["4", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64,
                          "temporal_overlap": 8}},
        "20": {"class_type": "CreateVideo", "inputs": {"images": ["18", 0], "fps": FPS}},
        SAVE_NODE: {"class_type": "SaveVideo",
                    "inputs": {"video": ["20", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }
    if mode == "guide":
        # Head Swap / LMS: the aligned source video is a guide anchored at frame 0 (MiniMaxH3AddGuide), not a reference video
        del g["12"]["inputs"]["ref_videos.ref_video_0"]
        g["ag"] = {"class_type": "MiniMaxH3AddGuide",
                   "inputs": {"positive": ["12", 0], "vae": ["4", 0], "latent": ["12", 1], "image": ["10", 0], "frame_idx": 0}}
        g["16"]["inputs"]["conditioning"] = ["ag", 0]
    if not use_ref_image:
        del g["12"]["inputs"]["ref_images.ref_image_0"]
        del g["img0"]
    last = ["3", 0]
    if q["lora"]:
        g["3b"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": last, "lora_name": q["lora"][0], "strength_model": q["lora"][1]}}
        last = ["3b", 0]
    for i, (name, strength) in enumerate(extra_loras or []):
        g[f"3x{i}"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": last, "lora_name": name, "strength_model": strength}}
        last = [f"3x{i}", 0]
    if control:  # H3 Fun ControlNet-Union fed with a control video of the original scene (edges, here)
        g["cn_l"] = {"class_type": "ModelPatchLoader", "inputs": {"name": control["patch"]}}
        g["cn_v"] = {"class_type": "LoadVideo", "inputs": {"file": control["video"]}}
        g["cn_c"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["cn_v", 0]}}
        g["cn"] = {"class_type": "MiniMaxH3FunControlNetApply",
                   "inputs": {"model": last, "model_patch": ["cn_l", 0], "vae": ["4", 0], "strength": float(control["strength"]),
                              "start_percent": 0.0, "end_percent": 1.0, "control_video": ["cn_c", 0]}}
        last = ["cn", 0]
    g["16"]["inputs"]["model"] = last
    return g
