"""Assembles a MiniMax H3 Ref2VA six-section prompt string from a video's
characters + base_prompt plus one clip's shot-specific detailed_description,
and merges a video's template_settings + a clip's own fields into a full
WanGP settings dict ready for shared.api's session.submit_task().

subject_definitions and retention_analysis are NOT free text — they're
always derived from the video's characters list, so identity/wardrobe/
reference wiring stays consistent instead of being retyped by hand per
video. Reference field names (image_refs, video_guide[2], audio_guide[2])
and the video_prompt_type/audio_prompt_type letters that activate them come
from models/minimax_h3/minimax_h3_handler.py's reference_mode block —
confirmed from source, not guessed:
  - image_refs: list[str], activated by "I" (or "KI") in video_prompt_type.
  - video_guide / video_guide2: single paths, activated by "V-" (one) or
    "V+-" (two) in video_prompt_type. Max 2 total.
  - audio_guide / audio_guide2: single paths, activated by "A" (one) or
    "AB" (two) in audio_prompt_type. Max 2 total.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SECTION_ORDER = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

DEFAULT_BASE_PROMPT = {
    "summary": "",
    "overall_soundscape": "",
    "non_diegetic_music": "",
}

# Known-good defaults, taken from the proven mansion-entrance debug settings
# (prompts_reference/mansion_entrance/settings_full_model_debug320p.json).
# A video's template_settings overrides whatever it specifies on top of this.
DEFAULT_TEMPLATE_SETTINGS = {
    "model_type": "minimax_h3_ref2va",
    "model_filename": "https://huggingface.co/DeepBeepMeep/MiniMax-H3/resolve/main/MiniMax-H3-Ref2VA_int8_convrot.safetensors",
    "resolution": "1280x704",
    "num_inference_steps": 20,
    "flow_shift": 12.0,
    "sample_solver": "euler",
    "skip_steps_cache_type": "first_block",
    "skip_steps_multiplier": 0.08,
    "skip_steps_start_step_perc": 25,
    "override_profile": 5,
    "override_attention": "sol",
    "video_prompt_type": "",
    "audio_prompt_type": "VV",
    # shared.api's task validation is stricter than the `wgp.py --process`
    # CLI path: it hard-rejects overlap 0 ("Windows Frames Overlap must be
    # at least 1") even for a single-window clip where overlap is a no-op.
    "sliding_window_overlap": 1,
    "sliding_window_color_correction_strength": 0,
    "sliding_window_overlap_noise": 0,
    "sliding_window_discard_last_frames": 0,
    "sliding_window_trim_first_frames": 0,
    "image_refs_relative_size": 100,
    "remove_background_images_ref": 1,
}

DEFAULT_VIDEO_LENGTH = 362  # ~15s @ 24fps, the single-sliding-window ceiling

# Applied to every generation's detailed_description, not just characters with
# a stylized (cartoon) reference — all subjects here are meant to render as
# real photorealistic people, so this is baseline quality language, not a
# one-off fix. From prompts_reference/h3_quality_presets.md's cinematic_realistic
# block.
CINEMATIC_REALISM_PRESET = (
    "Photorealistic, cinematic color grading, natural film grain, realistic "
    "skin texture and lighting, no over-smoothing or plastic look, no cartoon "
    "or illustrated rendering anywhere in the shot."
)

_UPSCALE_STATUS = {"status": "none", "job_id": None, "output_path": None, "error": None}

DEFAULT_CHARACTER = {
    "name": "",
    "identity_description": "",
    "wardrobe_notes": "",
    "retention": "fully_preserved",
    "references": [],
    # Reference-video "studio": any number of small generated videos from
    # this character's raw refs (a neutral turnaround, an angry close-up, a
    # specific pose...), each independently upscalable and frame-pickable.
    "reference_videos": [],
    # Which entry in reference_videos[] (if any) substitutes for this
    # character's raw references in real clip/other-reference-video
    # generations — at most one at a time, replaces the old boolean
    # use_reference_video (which only made sense with a single video).
    "active_reference_video_id": None,
}

# Template for one entry appended to a character's reference_videos[] list.
# Four separate inputs, joined into one detailed_description at generation
# time — each reusable independently of the others:
#   - style_prompt: rendering style (photorealistic vs. cartoon/illustrated,
#     color grading, film grain...) — defaults to CINEMATIC_REALISM_PRESET,
#     but editable per entry (e.g. deliberately go cartoonish for a
#     stylized character instead of always forcing photorealism).
#   - environment_prompt: background/lighting/setting.
#   - character_prompt: the character's static aspect/demeanor in this
#     capture (expression, stance, how they hold themselves) — no timing,
#     no shot structure, so it can be reused across different actions.
#   - action_prompt: the shot structure itself (framing, camera cuts/
#     timing, [Shot N] blocks, dialogue) — the thing that actually changes
#     most often between reference-video generations.
DEFAULT_REFERENCE_VIDEO = {
    "id": "",
    "name": "",
    "style_prompt": CINEMATIC_REALISM_PRESET,
    "environment_prompt": "",
    "character_prompt": "",
    "action_prompt": "",
    "seed": -1,
    "video_length": 174,
    "status": "none",
    "job_id": None,
    "output_path": None,
    "error": None,
    "upscale": dict(_UPSCALE_STATUS),
}


class TooManyReferences(ValueError):
    pass


class UnknownPromptTags(ValueError):
    pass


_TAG_TOKEN_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)\]\]")


def expand_prompt_tags(text: str, tags_by_key: dict[str, str]) -> str:
    """Expands `[[key]]` tokens into their stored prompt-tag body text — a
    lightweight reusable-snippet system so repeated boilerplate (e.g. the
    "Neutral Latin American Spanish dubbing accent, no regional accent, no
    voseo, use tú" wording that recurs across many clips' dialogue
    instructions) can be edited once instead of retyped verbatim everywhere.
    Called on the fully-composed prompt string right before a generation is
    submitted (see main.py), not per-section, so a tag works no matter which
    free-text field it was typed into. Raises UnknownPromptTags (→ HTTP 400)
    listing any token that doesn't match a real tag, rather than silently
    sending the literal "[[key]]" text to the model."""
    unknown = sorted({key for key in _TAG_TOKEN_RE.findall(text) if key not in tags_by_key})
    if unknown:
        raise UnknownPromptTags(f"Unknown prompt tag(s): {', '.join(unknown)}")
    return _TAG_TOKEN_RE.sub(lambda m: tags_by_key[m.group(1)], text)


def find_reference_video(character: dict[str, Any], reference_video_id: str) -> dict[str, Any] | None:
    for rv in character.get("reference_videos") or []:
        if rv["id"] == reference_video_id:
            return rv
    return None


def effective_path(ref: dict[str, Any]) -> str:
    """A reference's (or reference-video's) upscale output if it finished,
    otherwise its own path/output_path — upscaling never mutates the
    original file, it just becomes preferred once done."""
    upscale = ref.get("upscale") or {}
    if upscale.get("status") == "done" and upscale.get("output_path"):
        return upscale["output_path"]
    return ref.get("path") or ref.get("output_path") or ""


def effective_references(character: dict[str, Any]) -> list[dict[str, Any]]:
    """A character's references, except when active_reference_video_id
    points at a completed entry in reference_videos[] — then that single
    video substitutes for the character's raw references entirely (one
    video slot instead of N raw image/video/audio refs)."""
    active_id = character.get("active_reference_video_id")
    if active_id:
        rv = find_reference_video(character, active_id)
        if rv is not None and rv.get("status") == "done" and rv.get("output_path"):
            return [{"type": "video", "path": effective_path(rv)}]
    return character.get("references") or []


def compose_references(characters: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten every character's references into the WanGP settings fields,
    numbering <Picture N>/<Video N>/<Audio N> within each type as we go (the
    same running-index scheme compose_subject_definitions uses)."""
    image_refs: list[str] = []
    video_refs: list[str] = []
    audio_refs: list[str] = []
    any_depth_transfer = False
    for character in characters:
        for ref in effective_references(character):
            path = effective_path(ref).strip()
            if not path:
                continue
            ref_type = ref.get("type")
            if ref_type == "image":
                image_refs.append(path)
            elif ref_type == "video":
                video_refs.append(path)
                if ref.get("depth_transfer"):
                    any_depth_transfer = True
            elif ref_type == "audio":
                audio_refs.append(path)

    if len(video_refs) > 2:
        raise TooManyReferences(f"H3 Ref2VA supports at most 2 video references total, got {len(video_refs)}")
    if len(audio_refs) > 2:
        raise TooManyReferences(f"H3 Ref2VA supports at most 2 audio references total, got {len(audio_refs)}")

    if not video_refs:
        video_prompt_type_extra = ""
    elif any_depth_transfer:
        # Experimental (2026-08-19): "DV" runs the video through WanGP's
        # DepthAnything preprocessing before feeding it in as a Control Video —
        # pure geometry/motion, no RGB/identity/appearance survives extraction.
        # Simplification: this is an all-or-nothing switch for the whole video
        # reference set, not per-reference — mixing one raw "V-" ref and one
        # depth ref across the 2 available slots isn't supported yet.
        video_prompt_type_extra = "DV"
    else:
        video_prompt_type_extra = "V-" if len(video_refs) == 1 else "V+-"
    audio_prompt_type_extra = "" if not audio_refs else ("A" if len(audio_refs) == 1 else "AB")

    return {
        "image_refs": image_refs,
        "video_guide": video_refs[0] if video_refs else None,
        "video_guide2": video_refs[1] if len(video_refs) > 1 else None,
        "audio_guide": audio_refs[0] if audio_refs else None,
        "audio_guide2": audio_refs[1] if len(audio_refs) > 1 else None,
        "video_prompt_type_extra": video_prompt_type_extra,
        "audio_prompt_type_extra": audio_prompt_type_extra,
    }


def _labeled_references(character: dict[str, Any], img_i: int, vid_i: int, aud_i: int):
    """Yield (label, note, ref) for each of a character's references, and
    return the updated running counters. A shared helper so
    compose_subject_definitions and compose_retention_analysis number
    <Picture N>/<Video N>/<Audio N> identically without sharing state —
    both call this with the same running counters in the same character
    order, so the numbers line up across both composed sections."""
    labeled = []
    for ref in effective_references(character):
        if not effective_path(ref).strip():
            continue
        ref_type = ref.get("type")
        note = (ref.get("note") or "").strip()
        if ref_type == "image":
            img_i += 1
            labeled.append((f"<Picture {img_i}>", note, ref))
        elif ref_type == "video":
            vid_i += 1
            labeled.append((f"<Video {vid_i}>", note, ref))
        elif ref_type == "audio":
            aud_i += 1
            labeled.append((f"<Audio {aud_i}>", note, ref))
    return labeled, img_i, vid_i, aud_i


def compose_model_tags(characters: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The full list of H3 model-level reference tags (<Subject N>/<Picture
    N>/<Video N>/<Audio N>) actually available for THIS video's current
    character roster, each with a human-readable description of what/who it
    points at — for a frontend "available tags" reference panel, since a
    human can't be expected to recompute this numbering by hand (it's
    global across the whole roster, not per-character — see the
    "never hardcode reference numbers" note in AGENTS.md). Reuses
    _labeled_references so the numbers are guaranteed to match exactly what
    compose_subject_definitions/compose_retention_analysis actually emit,
    rather than a second, potentially-drifting implementation."""
    tags: list[dict[str, str]] = []
    img_i = vid_i = aud_i = 0
    for index, character in enumerate(characters):
        name = character.get("name") or f"Character {index + 1}"
        tags.append({"tag": f"<Subject {index + 1}>", "description": f"{name} — character reference"})
        labeled, img_i, vid_i, aud_i = _labeled_references(character, img_i, vid_i, aud_i)
        for label, note, ref in labeled:
            kind = {"<Picture": "image", "<Video": "video", "<Audio": "audio"}[next(k for k in ("<Picture", "<Video", "<Audio") if label.startswith(k))]
            filename = Path(effective_path(ref)).name
            role = f" ({note})" if note else ""
            tags.append({"tag": label, "description": f"{name} — {kind} reference{role}: {filename}"})
    return tags


def compose_subject_definitions(characters: list[dict[str, Any]]) -> str:
    """Per MiniMax's own H3 prompt-writing guide, a reference that supplies
    only clothing/style (not identity) should not get a standalone callout —
    it's cited inline in the <Subject N> definition itself, e.g. "...whose
    identity comes from <Picture 1> and whose wardrobe comes from
    <Picture 2>." That's what a reference's `note` drives below."""
    lines = []
    img_i = vid_i = aud_i = 0
    for index, character in enumerate(characters):
        subject_n = index + 1
        name = character.get("name") or f"Character {subject_n}"
        identity = (character.get("identity_description") or "").strip()
        wardrobe = (character.get("wardrobe_notes") or "").strip()

        labeled, img_i, vid_i, aud_i = _labeled_references(character, img_i, vid_i, aud_i)
        identity_labels = [label for label, note, _ in labeled if not note]
        noted = [(label, note) for label, note, _ in labeled if note]
        labels_str = " and ".join(identity_labels) if identity_labels else "the reference material below"

        sentence = f"<Subject {subject_n}> is {name}, whose identity comes from {labels_str}"
        sentence += f", preserving {identity}" if identity else ""
        for label, note in noted:
            sentence += f", and whose {note} comes from {label}"
        sentence += "."
        if wardrobe:
            sentence += f" {wardrobe}"
        lines.append(sentence)
    return "\n".join(lines)


def compose_retention_analysis(characters: list[dict[str, Any]]) -> str:
    """Uses MiniMax's own controlled vocabulary (confirmed from their H3
    prompt-writing guide): fully_preserved / partially_preserved /
    attribute_transfer / weak_reference. A noted reference (wardrobe/style
    only, not identity) is an attribute_transfer, folded into the subject's
    own line rather than given a separate weak_reference entry."""
    lines = []
    img_i = vid_i = aud_i = 0
    for index, character in enumerate(characters):
        subject_n = index + 1
        retention = character.get("retention") or "fully_preserved"
        identity = (character.get("identity_description") or "").strip()
        detail = f" - {identity}" if identity else ""
        line = f"<Subject {subject_n}> (appears throughout): {retention}{detail}."

        labeled, img_i, vid_i, aud_i = _labeled_references(character, img_i, vid_i, aud_i)
        noted = [(label, note) for label, note, _ in labeled if note]
        if noted:
            transfers = "; ".join(f"attribute_transfer ({note}) from {label}" for label, note in noted)
            line += f" {transfers}."
        lines.append(line)
    return "\n".join(lines)


def compose_cardinality_directive(characters: list[dict[str, Any]]) -> str:
    """Auto-generated anti-duplication directive, built from whoever is
    actually in the video's character roster — not hand-retyped per clip.
    Real bug this exists to prevent (2026-08-18, Breaking-Bad-style scene,
    2 characters): cross-attention cloned Santamaria into two identical
    copies in frame despite a milder one-line "no duplicates" mention in
    the shot text; the fix that actually worked was this much more
    explicit, per-subject, repeated formula (matches the "Multi-Subject
    Cardinality" guidance elsewhere in this file, now made structural
    instead of something to remember to type by hand every time)."""
    names = [character.get("name") or f"Character {i + 1}" for i, character in enumerate(characters or [])]
    if not names:
        return ""
    if len(names) == 1:
        return (
            f"Strict single-instance cardinality: EXACTLY ONE {names[0]} exists in this scene, one person "
            f"total. There is NO duplicate {names[0]}, NO second {names[0]}, NO mirror image or double, NO "
            "cloning, NO twins, NO background extras, NO crowd. If in doubt, render fewer people, never more."
        )
    counts = " and ".join(f"EXACTLY ONE {name}" for name in names)
    no_dupes = " ".join(f"NO duplicate {name}, NO second {name}, NO mirror image or double of {name}," for name in names)
    return (
        f"Strict single-instance cardinality: {counts} exist in this scene, {len(names)} people total, no more. "
        f"{no_dupes} NO cloning of any subject, NO twins, NO background extras, NO crowd. If in doubt, render "
        "fewer people, never more."
    )


def active_characters_for_clip(video: dict[str, Any], clip: dict[str, Any]) -> list[dict[str, Any]]:
    """The character roster to actually compose this clip's prompt from.

    `clip["active_character_ids"]` lets a clip use only a subset of the
    video's full character list -- None/absent means "all of them" (the
    original, still-default behavior). Without this, a video with a
    character who only appears in some clips would have
    compose_retention_analysis auto-claim they "appear throughout" on every
    other clip too, which isn't just misleading text -- it's a real
    hallucination risk (the model gets told to render someone who was never
    meant to be in that shot). Filtering here, before the composition
    functions ever see the roster, means <Subject N>/<Picture N>/etc. get
    renumbered against just this clip's own subset too, not the full video's
    ids, since compose_subject_definitions/compose_retention_analysis/
    compose_references all number positionally from whatever list they're
    given."""
    characters = video.get("characters") or []
    active_ids = clip.get("active_character_ids")
    if active_ids is None:
        return characters
    active_id_set = set(active_ids)
    return [c for c in characters if c.get("id") in active_id_set]


def build_prompt_string(base_prompt: dict[str, str], characters: list[dict[str, Any]], shot_prompt: str) -> str:
    sections = {**DEFAULT_BASE_PROMPT, **(base_prompt or {})}
    sections["subject_definitions"] = compose_subject_definitions(characters or [])
    sections["retention_analysis"] = compose_retention_analysis(characters or [])
    cardinality = compose_cardinality_directive(characters or [])
    sections["detailed_description"] = "\n".join(p for p in (CINEMATIC_REALISM_PRESET, cardinality, shot_prompt or "") if p)
    return "\n".join(f"{key}:\n{sections.get(key, '')}" for key in SECTION_ORDER)


def _finalize_settings(
    template: dict[str, Any],
    characters: list[dict[str, Any]],
    prompt: str,
    seed: int,
    video_length: int,
    output_filename: str,
) -> dict[str, Any]:
    refs = compose_references(characters)

    video_prompt_type = template.get("video_prompt_type", "") or ""
    if refs["image_refs"] and "I" not in video_prompt_type:
        video_prompt_type += "I"
    video_prompt_type += refs["video_prompt_type_extra"]
    audio_prompt_type = (template.get("audio_prompt_type", "") or "") + refs["audio_prompt_type_extra"]

    settings = {
        **template,
        "prompt": prompt,
        "seed": int(seed),
        "video_length": video_length,
        "sliding_window_size": video_length,
        "batch_size": 1,
        "repeat_generation": 1,
        "multi_prompts_gen_type": "FG",
        "output_filename": output_filename,
        "image_refs": refs["image_refs"],
        "video_prompt_type": video_prompt_type,
        "audio_prompt_type": audio_prompt_type,
    }
    for key in ("video_guide", "video_guide2", "audio_guide", "audio_guide2"):
        if refs[key]:
            settings[key] = refs[key]
    return settings


def build_generation_settings(
    video: dict[str, Any],
    clip: dict[str, Any],
    previous_clip: dict[str, Any] | None = None,
    bridge_end_frame_path: str | None = None,
) -> dict[str, Any]:
    """previous_clip: the preceding clip (by order), passed in only when
    clip['continue_from_previous'] is set AND that preceding clip has a
    completed output — see main.py's generate_clip. When present, this
    isn't independent-clips-then-concat; it's real video continuation
    (H3's image_prompt_type "V" / video_source, confirmed from
    models/minimax_h3/minimax_h3_handler.py's image_prompt_types_allowed
    including "V" and wgp.py's own "Continue Video" UI option) — the model
    is given the tail of the previous clip's actual rendered output as
    context and generates new frames that literally continue from it,
    rather than starting fresh from just a shared character/scene
    description like every other clip in this app does.

    bridge_end_frame_path: when set (clip['bridge_to_next'] — see main.py),
    a still frame extracted from the NEXT clip's own first frame, passed as
    H3's image_end / "E" (end-frame conditioning, confirmed from wgp.py:
    `image_end` field, `end_frames_always_enabled` is True for H3 so "E"
    combines freely with "V"). This is what lets you edit/regenerate a
    middle clip and have it land back on the *existing*, untouched next
    clip's opening frame — instead of the next clip becoming a stale,
    visually-discontinuous dead end that also needs regenerating."""
    template = {**DEFAULT_TEMPLATE_SETTINGS, **(video.get("template_settings") or {})}
    characters = active_characters_for_clip(video, clip)
    prompt = build_prompt_string(video.get("base_prompt") or {}, characters, clip.get("shot_prompt") or "")
    video_length = int(clip.get("video_length") or DEFAULT_VIDEO_LENGTH)
    output_filename = f"{video['id']}_{clip['order']:03d}_{clip['id']}"
    settings = _finalize_settings(template, characters, prompt, clip.get("seed", -1), video_length, output_filename)

    if clip.get("continue_from_previous") and previous_clip and previous_clip.get("output_path"):
        image_prompt_type = settings.get("image_prompt_type", "") or ""
        if "V" not in image_prompt_type:
            image_prompt_type += "V"
        settings["image_prompt_type"] = image_prompt_type
        # Pass the previous clip's own segment (or output_path if first clip) so WanGP only loads
        # the required ~5s prefix rather than the entire cumulative history, preventing RAM exhaustion.
        source_path = previous_clip.get("own_segment_path") or previous_clip.get("output_path")
        settings["video_source"] = source_path
        keep_frames = clip.get("continuation_keep_frames")
        if keep_frames:
            settings["keep_frames_video_source"] = str(int(keep_frames))

    if bridge_end_frame_path:
        image_prompt_type = settings.get("image_prompt_type", "") or ""
        if "E" not in image_prompt_type:
            image_prompt_type += "E"
        settings["image_prompt_type"] = image_prompt_type
        settings["image_end"] = [bridge_end_frame_path]

    return settings


def build_upscale_settings(media_path: str, output_filename: str, scale: float = 1.5) -> dict[str, Any]:
    """Settings for a standalone FlashVSR spatial-upscale postprocessing pass
    over an already-generated video OR a single still image — wgp.py's
    edit_postprocessing mode auto-detects which from the file extension
    (has_image_file_extension/has_video_file_extension), same settings shape
    either way. Used both for upscaling a reference video before pulling
    frames from it, and for upscaling one already-picked frame directly."""
    from shared.api import build_media_postprocessing_settings

    return build_media_postprocessing_settings(
        media_path,
        spatial_upsampling=f"flashvsr{scale:g}",
        output_filename=output_filename,
    )


def build_reference_video_settings(video: dict[str, Any], character: dict[str, Any], reference_video: dict[str, Any]) -> dict[str, Any]:
    """Settings for one entry in a character's reference-video 'studio': a
    single-subject generation from just that character's raw refs (a
    turnaround, a specific pose/emotion, ...), meant to be scrubbed for
    frame captures and/or reused later as one video reference."""
    template = {**DEFAULT_TEMPLATE_SETTINGS, **(video.get("template_settings") or {})}
    # Always generate from the character's own RAW references, never from
    # any reference_videos entry (that would be self-referential).
    solo = [{**character, "active_reference_video_id": None}]
    style = (reference_video.get("style_prompt") or CINEMATIC_REALISM_PRESET).strip()
    environment = (reference_video.get("environment_prompt") or "").strip()
    character_aspect = (reference_video.get("character_prompt") or "").strip()
    action = (reference_video.get("action_prompt") or "").strip()
    detailed_description = "\n".join(p for p in (style, environment, character_aspect, action) if p)
    sections = {
        "subject_definitions": compose_subject_definitions(solo),
        "summary": "[reference generation] A clean, isolated reference capture of the subject for reuse as a future generation reference.",
        "retention_analysis": compose_retention_analysis(solo),
        "detailed_description": detailed_description,
        "overall_soundscape": "Quiet, neutral studio ambience.",
        "non_diegetic_music": "None.",
    }
    prompt = "\n".join(f"{key}:\n{sections.get(key, '')}" for key in SECTION_ORDER)
    video_length = int(reference_video.get("video_length") or DEFAULT_VIDEO_LENGTH)
    output_filename = f"{video['id']}_char_{character['id']}_ref_{reference_video['id']}"
    return _finalize_settings(template, solo, prompt, reference_video.get("seed", -1), video_length, output_filename)
