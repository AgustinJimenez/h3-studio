"""Prompt builder for one swap pass.

Encodes the wording rules found while testing the character-swap LoRA (see AGENTS.md):
  * always the long explicit form (the bare one-sentence prompt did nothing on hard footage);
  * one replacement per pass; a later pass identifies its target by what he looks like NOW;
  * everyone else is protected by appearance plus their own outfit (never by clothes that were
    replaced, never naming an outfit without saying whose it is);
  * one fixed outfit sentence per character, repeated verbatim in every scene;
  * the background text only describes what is really there, followed by a fixed clause that
    forbids rays, beams, gradients and darkening.
"""

from __future__ import annotations

import re
from typing import Any

CLEAN_CLAUSE = (
    "No light rays, no beams, no streaks, no translucent overlays and no colour gradients anywhere in the frame: "
    "the clothes have flat, uniform colour. Keep the overall brightness, contrast and colour grading exactly as in "
    "<Video 1>; do not darken or tint the picture. Do not add any door, cabinet, window or furniture."
)
KEEP_CLAUSE = (
    "Preserve the source video's camera and framing. Match each person's position, scale, pose and movement "
    "throughout the clip. Copy the exact facial expression, mouth movement and eye direction of the person in "
    "<Video 1> frame by frame: if that person is chewing, looking or has a closed mouth, the new character does not speak. "
    "Do not show the reference photo or its background."
)
LIGHT_CLAUSE = (
    "Light the new character exactly like the rest of <Video 1>: the same light direction, colour temperature, softness "
    "and contrast as the background, so the person blends into the scene and is not brighter, flatter or cut out."
)
DEFAULT_BACKGROUND = "The background and the room must stay exactly as in <Video 1>."

# Naming a feature the scene lacks makes the model invent it ("keep the stripes" grew light rays in a striped-less scene).
_RISKY = ("stripe", "ray", "beam", "door", "window", "cabinet")


class PromptError(ValueError):
    pass


def clean_look(text: str) -> str:
    """A character profile made for the clip editor also describes the voice ("... and voice - voice must match the audio
    reference ..."). A swap keeps the original audio, so nothing about voices or audio belongs in its prompt."""
    t = re.sub(r"\s+[-–—]\s+[^.;]*\b(?:voice|audio)\b.*$", "", text or "", flags=re.I)
    t = re.sub(r"[^.;]*\baudio\b[^.;]*[.;]?", "", t, flags=re.I)
    t = re.sub(r"\b(?:(?:a|an|the|his|her)\s+)?(?:\w+\s+)?voice\b(?:\s+and\b)?", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"[\s,;]+(?:and\s*)?$", "", t).strip()


def background_warnings(text: str) -> list[str]:
    low = (text or "").lower()
    return [w for w in _RISKY if w in low]


def build_pass_prompt(person: dict[str, Any], cast: dict[str, dict[str, Any]], scene_people: list[dict[str, Any]],
                      background_text: str) -> str:
    entry = cast.get(person.get("cast_id"))
    if entry is None:
        raise PromptError(f"cast entry {person.get('cast_id')!r} not found")
    outfit = (entry.get("outfit") or "").strip()
    if not outfit:
        raise PromptError(f"{entry.get('name') or 'this character'} has no outfit text")
    target = (person.get("target_description") or "").strip()
    if not target:
        raise PromptError("the person to replace has no description")
    has_glasses = "glass" in " ".join(str(entry.get(k) or "") for k in ("appearance", "outfit", "body")).lower()
    head_of_character = ("the head, hair, face and glasses of the character in <Picture 1>." if has_glasses else
                         "the head, hair and face of the character in <Picture 1>. The new character wears no glasses and no eyewear of any kind: "
                         "the eyes and eyebrows are fully visible and bare.")
    parts = [
        f"Replace only {target} in <Video 1> with the character in <Picture 1>.",
        "Replace that person's entire head, including hair and face, with " + head_of_character,
        f"In every shot this character wears exactly the same outfit: {outfit}.",
        "Replace that person's clothes, hat and accessories too: nothing the person wears in <Video 1> is kept.",
    ]
    look = clean_look(entry.get("appearance") or "").rstrip(".")
    if look:
        parts.append(f"The new character is {look}; none of the original person's hair colour, hairstyle or face is kept.")
    body = (entry.get("body") or "").strip()
    if body:
        parts.append(f"The character is {body}; give them that body, with its height, width and proportions, and fit the clothes to it, "
                     "not the build of the person in <Video 1>.")
    for other in sorted(scene_people, key=lambda p: p["order"]):
        if other["id"] == person["id"]:
            continue
        other_target = (other.get("target_description") or "").strip()
        if other["order"] < person["order"]:
            # already swapped: recognise him by the new character's look and protect the outfit we gave him
            oc = cast.get(other.get("cast_id")) or {}
            who = clean_look(oc.get("appearance") or "") or other_target
            oc_outfit = (oc.get("outfit") or "").strip()
            keeps = f", keeping {oc_outfit} and all of their colours unchanged" if oc_outfit else ""
            parts.append(f"Leave {who} exactly as they are{keeps}.")
        else:
            parts.append(f"Leave {other_target} exactly as they are.")
    parts.append((background_text or "").strip() or DEFAULT_BACKGROUND)
    parts += [LIGHT_CLAUSE, CLEAN_CLAUSE, KEEP_CLAUSE]
    return " ".join(parts)
