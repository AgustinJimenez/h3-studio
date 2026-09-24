"""Real WanGP-sourced dropdown choices for template_settings (resolution,
attention mode, memory profile, model type/checkpoint), instead of free-text
fields the frontend previously let the user mistype. Pulled live from the
already-loaded WanGP runtime via `shared.api`'s private
`WanGPSession._ensure_runtime()` (`runtime.module` is the actual `wgp`
module) — the exact same functions and lists WanGP's own Gradio UI uses to
build its own dropdowns (`get_resolution_choices`, `attention_modes_choices`,
`memory_profile_choices`), not reimplemented or guessed.

This app only supports Ref2VA (not FL2VA/text-to-video), so model_type
choices are filtered to Ref2VA variants only.
"""

from __future__ import annotations

from typing import Any

REF2VA_SUBSTR = "ref2va"
FL2VA_SUBSTR = "fl2va"


def _choice_list(pairs) -> list[dict[str, Any]]:
    return [{"label": label, "value": value} for label, value in pairs]


def get_generation_options(session: Any, model_type: str | None = None) -> dict[str, Any]:
    from shared.api import _pushd

    runtime = session._ensure_runtime()
    mod = runtime.module

    model_defs = session.list_model_defs()
    ref2va_defs = [
        d for d in model_defs
        if REF2VA_SUBSTR in str(d.get("model_type") or "")
        and FL2VA_SUBSTR not in str(d.get("model_type") or "")
    ]
    def _filenames(urls: Any) -> list[str]:
        # A model_def's "URLs" is usually a list of checkpoint URLs, but WanGP
        # also allows a plain string meaning "inherit this other model_type's
        # weights" (e.g. the PDD variants reusing minimax_h3_ref2va's files).
        if urls is None:
            return []
        return [urls] if isinstance(urls, str) else list(urls)

    model_types = [
        {
            "model_type": d["model_type"],
            "name": d.get("name", d["model_type"]),
            "model_filenames": _filenames(d.get("URLs")),
        }
        for d in ref2va_defs
    ]

    selected_model_type = model_type or (model_types[0]["model_type"] if model_types else None)
    model_def = session.get_model_def(selected_model_type) if selected_model_type else None

    resolutions: list[dict[str, Any]] = []
    attention_modes: list[dict[str, Any]] = []
    memory_profiles = _choice_list([("Default Memory Profile", -1)] + list(mod.memory_profile_choices))

    if model_def is not None:
        with _pushd(runtime.root):
            resolution_choices, _ = mod.get_resolution_choices(None, model_def)
        resolutions = _choice_list(resolution_choices)

        attention_choices = [("Default Attention Mode", "")] + list(mod.attention_modes_choices)
        if model_def.get("sol_attention", False):
            # WanGP's own UI only offers "sol" conditionally (models.wgp:12453) —
            # replicated here rather than always showing it, since offering an
            # attention mode a model doesn't support would defeat the point of
            # sourcing real choices instead of free text.
            attention_choices.append(("sol: Sol sparse attention (Triton, RTX 40xx+)", "sol"))
        attention_modes = _choice_list(attention_choices)

    loras: list[str] = []
    if selected_model_type is not None:
        loras = list(session.list_loras(selected_model_type).get("loras") or [])

    return {
        "model_types": model_types,
        "selected_model_type": selected_model_type,
        "resolutions": resolutions,
        "attention_modes": attention_modes,
        "memory_profiles": memory_profiles,
        "loras": loras,
    }
