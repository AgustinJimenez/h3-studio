from __future__ import annotations

from backend.swap import prompts

CAST = {
    "m": {"name": "Mapache", "outfit": "a light blue button-up collared shirt with the sleeves rolled up and plain khaki trousers",
          "body": "", "appearance": "the dark-haired heavyset man with glasses and a short beard"},
    "v": {"name": "Veron", "outfit": "a dark grey polo shirt with a small chest logo and plain dark trousers",
          "body": "a fat, heavyset man with a round full face", "appearance": "the heavyset man in the dark polo"},
}
P0 = {"id": "p0", "target_description": "the heavier man in the pink shirt", "cast_id": "m", "order": 0}
P1 = {"id": "p1", "target_description": "the older white-haired man", "cast_id": "v", "order": 1}


def test_long_explicit_form_with_outfit_and_fixed_clauses():
    t = prompts.build_pass_prompt(P0, CAST, [P0], "A plain beige wall.")
    assert t.startswith("Replace only the heavier man in the pink shirt in <Video 1> with the character in <Picture 1>.")
    assert "In every shot this character wears exactly the same outfit: a light blue button-up collared shirt" in t
    assert "A plain beige wall." in t
    assert prompts.CLEAN_CLAUSE in t and prompts.KEEP_CLAUSE in t
    assert "No light rays, no beams, no streaks" in t and "Do not show the reference photo" in t
    assert t.index("A plain beige wall.") < t.index(prompts.CLEAN_CLAUSE) < t.index(prompts.KEEP_CLAUSE)


def test_body_sentence_only_when_set():
    assert "The character is a fat, heavyset man" in prompts.build_pass_prompt(P1, CAST, [P1], "")
    assert "The character is" not in prompts.build_pass_prompt(P0, CAST, [P0], "")


def test_empty_background_falls_back_to_keep_the_room():
    assert "The background and the room must stay exactly as in <Video 1>." in prompts.build_pass_prompt(P0, CAST, [P0], "  ")


def test_errors_are_clear():
    for bad in ({**CAST, "m": {**CAST["m"], "outfit": "  "}}, {}):
        try:
            prompts.build_pass_prompt(P0, bad, [P0], "")
        except prompts.PromptError as exc:
            assert str(exc)
        else:
            raise AssertionError("expected PromptError")


def test_later_pass_protects_the_earlier_one_by_appearance_and_outfit_not_by_old_clothes():
    t = prompts.build_pass_prompt(P1, CAST, [P0, P1], "")
    assert "Leave the dark-haired heavyset man with glasses and a short beard exactly as they are" in t
    assert "keeping a light blue button-up collared shirt" in t and "all of their colours unchanged" in t
    assert "pink shirt" not in t  # the swapped man's ORIGINAL clothes must not appear


def test_first_pass_protects_the_not_yet_swapped_one_by_description_only():
    t = prompts.build_pass_prompt(P0, CAST, [P0, P1], "")
    assert "Leave the older white-haired man exactly as they are." in t
    assert "dark grey polo" not in t  # that outfit belongs to the character who replaces him later


def test_protect_falls_back_to_target_description_without_appearance():
    cast = {**CAST, "m": {**CAST["m"], "appearance": ""}}
    t = prompts.build_pass_prompt(P1, cast, [P0, P1], "")
    assert "Leave the heavier man in the pink shirt exactly as they are" in t  # only path left; user chose to describe him so


def test_background_warnings_flag_features_the_scene_may_lack():
    assert prompts.background_warnings("the same stripes and a door") == ["stripe", "door"]
    assert prompts.background_warnings("a plain beige wall") == []
    assert prompts.background_warnings("dark studio with lit screens") == []


def test_prompt_forbids_keeping_any_clothes_from_the_video():
    # User feedback: the swapped character must wear its own reference outfit, not clothes from the source video.
    cast = {"c1": {"id": "c1", "name": "A", "appearance": "a tall man", "outfit": "a red coat", "body": ""}}
    person = {"id": "p1", "cast_id": "c1", "target_description": "the man on the left", "order": 0}
    out = prompts.build_pass_prompt(person, cast, [person], "")
    assert "nothing the person wears in <Video 1> is kept" in out
    assert out.index("wears exactly the same outfit: a red coat") < out.index("nothing the person wears")


def test_no_glasses_unless_the_character_has_them_and_lighting_matches_the_scene():
    # User feedback: characters without glasses came out wearing glasses; the new person was lit differently from the room.
    plain = {"c1": {"id": "c1", "name": "A", "appearance": "a tall man", "outfit": "a red coat", "body": ""}}
    glassy = {"c1": {"id": "c1", "name": "A", "appearance": "a tall man with round glasses", "outfit": "a red coat", "body": ""}}
    person = {"id": "p1", "cast_id": "c1", "target_description": "the man on the left", "order": 0}
    a = prompts.build_pass_prompt(person, plain, [person], "")
    b = prompts.build_pass_prompt(person, glassy, [person], "")
    assert "wears no glasses" in a and "no eyewear of any kind" in a and "glasses (if any)" not in a
    assert "wears no glasses" not in b and "and glasses of the character" in b
    for out in (a, b):
        assert "same light direction" in out


def test_prompt_states_the_characters_look_and_forbids_the_original_hair():
    # User feedback: the first frames of a swapped clip kept the original person's red hair.
    cast = {"c1": {"id": "c1", "name": "A", "appearance": "a woman with long dark hair", "outfit": "a pink shirt", "body": ""}}
    person = {"id": "p1", "cast_id": "c1", "target_description": "the woman with red hair", "order": 0}
    out = prompts.build_pass_prompt(person, cast, [person], "")
    assert "The new character is a woman with long dark hair" in out
    assert "none of the original person's hair colour, hairstyle or face is kept" in out


def test_prompt_copies_the_original_expression_and_mouth_movement():
    # User feedback: the swapped character talked while the original person was only chewing and looking.
    cast = {"c1": {"id": "c1", "name": "A", "appearance": "a tall man", "outfit": "a red coat", "body": ""}}
    person = {"id": "p1", "cast_id": "c1", "target_description": "the man", "order": 0}
    out = prompts.build_pass_prompt(person, cast, [person], "")
    assert "exact facial expression, mouth movement and eye direction" in out and "does not speak" in out


def test_body_build_overrides_the_source_persons_build():
    # User feedback: a heavy-set character came out slim in wide shots because the source person is slim.
    cast = {"c1": {"id": "c1", "name": "A", "appearance": "a tall man", "outfit": "a red coat", "body": "heavy-set with a round belly"}}
    person = {"id": "p1", "cast_id": "c1", "target_description": "the slim man", "order": 0}
    out = prompts.build_pass_prompt(person, cast, [person], "")
    assert "The character is heavy-set with a round belly;" in out and "not the build of the person in <Video 1>" in out
    assert "height, width and proportions" in out


VOICE_LOOK = "her exact facial identity, dark hair, build, and voice - voice must match the audio reference closely, not a generic or different-sounding voice"


def test_voice_text_from_a_clip_profile_never_reaches_the_swap_prompt():
    cast = {"l": {"name": "Lafi", "outfit": "a pink t-shirt", "body": "", "appearance": VOICE_LOOK}}
    p = {"id": "p", "target_description": "the woman", "cast_id": "l", "order": 0}
    t = prompts.build_pass_prompt(p, cast, [p], "")
    assert "voice" not in t.lower() and "audio" not in t.lower()
    assert "her exact facial identity, dark hair, build" in t
    # also when she is the protected, already swapped person in another pass
    other = {"id": "q", "target_description": "the man", "cast_id": "m", "order": 1}
    t2 = prompts.build_pass_prompt(other, {**cast, "m": {"name": "M", "outfit": "a shirt", "body": "", "appearance": "a man"}}, [p, other], "")
    assert "voice" not in t2.lower()


def test_clean_look_keeps_ordinary_descriptions_untouched():
    assert prompts.clean_look("a slim woman with long dark hair") == "a slim woman with long dark hair"
    assert prompts.clean_look("a man with a deep voice and a beard") == "a man with a beard"
    assert prompts.clean_look("") == ""


def test_closed_mouths_stay_still_and_closed():
    t = prompts.build_pass_prompt(P0, CAST, [P0], "")
    assert "no chewing" in t and "lips together" in t


def test_orientation_of_the_person_is_kept():
    t = prompts.build_pass_prompt(P0, CAST, [P0], "")
    assert "faces away from the camera" in t and "does not turn around" in t


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
