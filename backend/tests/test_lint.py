"""Run with:  python -m backend.tests.test_lint   (also collected by pytest if you have it)."""

from __future__ import annotations

from backend import lint

MAPACHE = {"id": "m", "name": "Mapache", "retention": "fully_preserved",
           "identity_description": "round face, goatee, black-framed glasses",
           "wardrobe_notes": "A faded grey t-shirt and dark sweatpants, barefoot.",
           "references": [{"type": "image", "path": "C:/x/mapache.png"}]}
ROOM = {"id": "r", "name": "living room", "kind": "environment", "retention": "fully_preserved",
        "identity_description": "a dark living room", "references": [{"type": "image", "path": "C:/x/room.png"}]}


def _video(**template):
    return {"id": "v", "template_settings": {"resolution": "960x544", **template}, "base_prompt": {},
            "characters": [MAPACHE, ROOM]}


def _clip(shot_prompt="A calm shot.", length=192, **extra):
    return {"id": "c", "order": 1, "shot_prompt": shot_prompt, "video_length": length, "seed": 1, **extra}


def _codes(findings):
    return [f["code"] for f in findings]


# --- frame grid: expected values are what WanGP really delivered for 133 past clips of this app

def test_rendered_frames_matches_what_wangp_delivered():
    delivered = {125: 124, 145: 141, 240: 226, 174: 158, 289: 277, 337: 328, 193: 192,
                 124: 124, 141: 141, 243: 243, 345: 345, 362: 362, 4: 5}
    for requested, expected in delivered.items():
        assert lint.rendered_frames(requested) == expected, requested


def test_legal_lengths_are_the_fifteen_grid_values():
    assert lint.legal_lengths() == [124, 141, 158, 175, 192, 209, 226, 243, 260, 277, 294, 311, 328, 345, 362]
    assert lint.seconds(362) == 362 / 24  # 15.083 s, the longest single take


def test_length_findings():
    assert not {"G1", "G2", "G3"} & set(_codes(lint.lint_clip(_video(), _clip(length=192))["findings"]))
    assert not {"G1", "G2", "G3"} & set(_codes(lint.lint_clip(_video(), _clip(length=362))["findings"]))
    assert "G1" in _codes(lint.lint_clip(_video(), _clip(length=174))["findings"])      # the app's old default
    assert "G2" in _codes(lint.lint_clip(_video(), _clip(length=97))["findings"])       # below the 124 minimum
    assert "G3" in _codes(lint.lint_clip(_video(), _clip(length=380))["findings"])      # above the trained range


def test_lint_reports_the_rendered_length():
    report = lint.lint_clip(_video(), _clip(length=174))
    assert (report["requested_frames"], report["rendered_frames"]) == (174, 158)
    assert report["rendered_seconds"] == round(158 / 24, 3)


# --- shot timing

def test_cut_time_parsing():
    assert lint.cut_time(" At 00:05.000, the shot cuts to a close-up") == 5.0
    assert lint.cut_time("At 00:08 the camera") == 8.0
    assert lint.cut_time("At 1:02.5, ") == 62.5
    assert lint.cut_time("The camera cuts") is None


def test_shot_timing_rules():
    two = "[Shot 1] A wide shot of Mapache in his grey t-shirt. [Shot 2] {} A close-up of Mapache in his grey t-shirt."
    ok = _codes(lint.lint_clip(_video(), _clip(two.format("At 00:04.000,"), 192))["findings"])
    assert not {"T1", "T2", "T3"} & set(ok)
    assert "T1" in _codes(lint.lint_clip(_video(), _clip(two.format(""), 192))["findings"])
    assert "T2" in _codes(lint.lint_clip(_video(), _clip(two.format("At 00:00.500,"), 192))["findings"])
    assert "T3" in _codes(lint.lint_clip(_video(), _clip(two.format("At 00:07.500,"), 192))["findings"])  # 192 frames = 8 s


def test_single_shot_needs_no_timing():
    assert not {"T1", "T2", "T3", "W1"} & set(_codes(lint.lint_clip(_video(), _clip("[Shot 1] Mapache sits."))["findings"]))


# --- wardrobe drift

def test_wardrobe_must_be_restated_in_every_shot():
    drift = "[Shot 1] Mapache in his grey t-shirt sits. [Shot 2] At 00:04.000, Mapache raises the can."
    fixed = "[Shot 1] Mapache in his grey t-shirt sits. [Shot 2] At 00:04.000, Mapache in his grey t-shirt raises the can."
    hits = [f for f in lint.lint_clip(_video(), _clip(drift))["findings"] if f["code"] == "W1"]
    assert len(hits) == 1 and "[Shot 2]" in hits[0]["message"]
    assert "W1" not in _codes(lint.lint_clip(_video(), _clip(fixed))["findings"])


def test_wardrobe_ignores_shots_that_do_not_name_the_character():
    empty_room = "[Shot 1] Mapache in his grey t-shirt sits. [Shot 2] At 00:04.000, the empty hallway glows."
    assert "W1" not in _codes(lint.lint_clip(_video(), _clip(empty_room))["findings"])


# --- prompt / canvas

def test_canvas_rules():
    assert "C1" in _codes(lint.lint_clip(_video(resolution="970x540"), _clip())["findings"])
    assert "C2" in _codes(lint.lint_clip(_video(resolution="1920x1088"), _clip())["findings"])
    assert not {"C1", "C2"} & set(_codes(lint.lint_clip(_video(resolution="960x544"), _clip())["findings"]))


def test_a_broken_clip_is_reported_not_raised():
    report = lint.lint_clip({"id": "v"}, {"id": "c"})  # no characters/order: build fails
    assert "P0" in _codes(report["findings"])


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
