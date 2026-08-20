"""Settings composition for Wan2.2-Animate's "Replacement mode" — the
Animate equivalent of prompt.py, kept deliberately separate from it.

Unlike MiniMax H3 (a generate-from-scratch model driven by a composed
6-section prompt string + <Subject/Picture/Video/Audio N> reference tags),
Wan2.2-Animate is a letter-code model (like VACE): a `video_prompt_type`
string of single-letter flags selects behavior, and the real inputs are a
driving/control video (`video_guide`) + a character identity photo
(`image_refs`) + a plain-text prompt. There is no shared composition logic
with H3 worth factoring out.

Letter meanings for base architecture "animate" (traced in wan_handler.py
and wgp.py's generic guide-prep pipeline):
  P - pose-preprocess the control video
  V - master "use a control video" toggle (makes video_guide required)
  B - extract face movements from the control video into a face-motion tensor
  A - "masked area" mode (makes video_mask meaningful)
  I - image_refs = identity/character reference image(s)
  H - convert the mask to a bounding box rather than using its raw shape
  # - Gradio-only marker revealing the "Apply Relighting" checkbox; by
      itself a no-op headlessly. The relighting LoRA (this model's sole
      preload_URLs entry) only loads when BOTH "#" and "1" are present
      (models/wan/any2video.py) -- "1" is the real relighting toggle.

Replacement mode = "PVBAIH#" (bbox-ified mask) or "PVBAI#" (raw mask shape,
"see through mask" variant) -- both keep the control video's own
background, unlike the Animation-mode presets which also carry "K" to
composite a new background from image_refs[0].

Known limitation, not fully fixed here: WanGP has no headless
auto-segmentation. Real per-person masks come only from WanGP's interactive
Gradio tools (Magic Mask / Matanyone), unreachable through the headless
session.submit() path used here. `mask_path` is accepted as an optional
pass-through for a mask produced some other way.

`forced_guide_mask_inputs` does NOT mean WanGP silently accepts a missing
mask, contrary to initial research -- confirmed empirically (wgp.py's own
input validation): with Replacement mode's "A" letter present, video_mask
is a hard requirement; generation fails outright ("You must provide a Video
Mask") if it's absent. main.py::generate_animate_job works around this by
materializing a plain white full-frame mask video via ffmpeg when the job
has no mask_path, matching the control video's own resolution/fps/duration
-- white (mask value 1) is the "replace this area" convention per
shared/utils/utils.py's prepare_video_guide_and_mask. So "leave mask_path
blank" still means "full frame", just via an explicit generated file
instead of an implicit model default. Whether full-frame masking (vs. a
real per-person mask) gives acceptable Replacement-mode quality is the
first real empirical question for this feature -- see AGENTS.md.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ANIMATE_SETTINGS: dict[str, Any] = {
    "model_type": "animate",
    "model_filename": "https://huggingface.co/DeepBeepMeep/Wan2.2/resolve/main/wan2.2_animate_14B_quanto_bf16_int8.safetensors",
    "resolution": "832x480",
    "num_inference_steps": 20,
    "flow_shift": 7.0,
    "video_length": 81,
    "sliding_window_size": 81,  # model's own docs recommend >=81 for style continuity; not auto-set by wan_handler.py
    "force_fps": "control",  # output fps follows video_guide's own fps (this model defaults to fps=30 internally)
    "mask_expand": 20,
    "remove_background_images_ref": 0,  # no_background_removal=True for this model; keep the identity photo as-is
    "audio_prompt_type": "R",  # inherited default; Replacement mode exposes no audio-guide fields
}


def build_animate_settings(job: dict[str, Any]) -> dict[str, Any]:
    base = "PVBAIH#" if job.get("mode", "replace") == "replace" else "PVBAI#"
    video_prompt_type = base + ("1" if job.get("relighting") else "")

    settings: dict[str, Any] = {
        **DEFAULT_ANIMATE_SETTINGS,
        "video_prompt_type": video_prompt_type,
        "video_guide": job["control_video_path"],
        "image_refs": [job["character_image_path"]],
        "prompt": job.get("prompt") or "",
        "seed": job.get("seed", -1),
        "output_filename": f"animate_{job['id']}",
    }
    if job.get("video_length"):
        settings["video_length"] = job["video_length"]
        settings["sliding_window_size"] = job["video_length"]
    if job.get("resolution"):
        settings["resolution"] = job["resolution"]
    if job.get("mask_path"):
        settings["video_mask"] = job["mask_path"]
    return settings
