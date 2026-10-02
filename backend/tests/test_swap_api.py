from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.swap import api, scenes, store


class FakeJobStore:
    def __init__(self):
        self.submitted: list[dict] = []

    def submit_callable(self, runner, dest_path, on_done, on_queued=None, on_running=None, on_cancel=None):
        job_id = f"job{len(self.submitted)}"
        self.submitted.append({"job_id": job_id, "runner": runner, "on_done": on_done})
        if on_queued:
            on_queued(job_id)
        return job_id


class FakeClient:
    def __init__(self):
        self.interrupted = 0
        self.freed = 0

    def interrupt(self):
        self.interrupted += 1

    def free(self):
        self.freed += 1


def _three_scene_video(path: Path) -> str:
    ff = scenes.ffmpeg_exe()
    parts = []
    with tempfile.TemporaryDirectory() as d:
        for i, color in enumerate(["white", "black", "0x808080"]):
            p = Path(d) / f"{i}.mp4"
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=96x160:r=24",
                            "-frames:v", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
            parts.append(p)
        lst = Path(d) / "l.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
        subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=3", "-c:v", "copy", "-c:a", "aac", "-shortest", str(path)], check=True)
    return str(path)


def _clip(path: Path, frames: int) -> str:
    subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x808080:s=96x160:r=24",
                    "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


def _env():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    store.ROOT = root / "swaps"
    app = FastAPI()
    app.include_router(api.router)
    js = FakeJobStore()
    client_fake = FakeClient()
    api.set_job_store(js, release_wangp=lambda: None, client_factory=lambda: client_fake)
    api._characters_provider = lambda: [{"video_id": "v", "video_title": "V", "character_id": "ch1", "name": "Lafi",
                                          "image_path": "lafi.png", "appearance": "a slim woman", "outfit": "a green dress"}]
    video = _three_scene_video(root / "src.mp4")
    return tmp, TestClient(app), js, client_fake, video


def _create(tc, video):
    with open(video, "rb") as fh:
        r = tc.post("/swaps", data={"title": "Test Clip"}, files={"file": ("src.mp4", fh, "video/mp4")})
    assert r.status_code == 200, r.text
    return r.json()


def _setup_project(tc, video):
    p = _create(tc, video)
    pid = p["id"]
    d = tc.post(f"/swaps/{pid}/detect-scenes").json()
    cast = [{"id": "c1", "name": "Lafi", "image_path": "lafi.png", "appearance": "a slim woman", "outfit": "a green dress", "body": "slim"}]
    scn = [{"index": 0, "background_text": "", "people": [{"id": "p1", "cast_id": "c1", "target_description": "the man", "order": 0}]},
           {"index": 1, "background_text": "", "people": []},
           {"index": 2, "background_text": "", "people": [{"id": "p2", "cast_id": "c1", "target_description": "the man", "order": 0}]}]
    r = tc.patch(f"/swaps/{pid}", json={"cast": cast, "scenes": scn})
    assert r.status_code == 200, r.text
    return pid, d


def test_upload_creates_project_with_source_properties():
    tmp, tc, js, cl, video = _env()
    with tmp:
        p = _create(tc, video)
        assert p["source"]["frames"] == 72 and p["source"]["has_audio"] is True and p["source"]["width"] == 96
        assert p["source_url"].startswith("/swap-media/") and Path(store.ROOT / p["folder"] / "source").exists()
        assert [x["id"] for x in tc.get("/swaps").json()] == [p["id"]]


def test_detect_scenes_finds_three_with_thumbnails():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, d = _setup_project(tc, video)
        assert [s["start_frame_src"] for s in d["scenes"]] == [0, 24, 48]
        assert all(s["thumb_url"] for s in d["scenes"])


def test_merge_reduces_scenes_and_recomputes_frames():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        r = tc.post(f"/swaps/{pid}/scenes/merge", json={"index": 0}).json()
        assert len(r["scenes"]) == 2 and r["scenes"][0]["frames_24"] == 48 and [s["index"] for s in r["scenes"]] == [0, 1]


def test_plan_builds_passes_and_notes_empty_scene():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        r = tc.post(f"/swaps/{pid}/plan").json()
        assert [p["scene_index"] for p in r["passes"]] == [0, 2] and r["plan_notes"]


def test_run_preview_scene_zero_submits_only_that_scene_and_leaves_other_scenes_alone():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/plan")
        r = tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        assert r.status_code == 200, r.text
        assert len(js.submitted) == 1
        passes = r.json()["passes"]
        assert passes[0]["status"] == "queued" and passes[0]["quality"] == "preview" and passes[0]["job_id"] == "job0"
        assert passes[0]["params"]["steps"] == 4
        # a per-scene quality change must not re-plan or re-quality the other scenes
        assert passes[1]["status"] == "draft" and passes[1]["quality"] == "final"
        assert r.json()["settings"]["quality"] == "final"


def test_run_other_quality_for_one_scene_keeps_finished_passes_of_other_scenes():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        passes = tc.post(f"/swaps/{pid}/plan").json()["passes"]
        store.update_pass(pid, passes[1]["id"], status="done", output_path="x.mp4", raw_path="y.mp4")
        r = tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0}).json()
        later = [p for p in r["passes"] if p["scene_index"] == 2][0]
        assert later["status"] == "done" and later["quality"] == "final" and later["output_path"] == "x.mp4"


def test_run_with_nobody_assigned_is_400_and_unknown_ids_404():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid = _create(tc, video)["id"]
        tc.post(f"/swaps/{pid}/detect-scenes")  # scenes, but nobody is assigned in any of them, so nothing is planned
        assert tc.post(f"/swaps/{pid}/run", json={"quality": "final", "scene_index": None}).status_code == 400
        assert tc.get("/swaps/nope").status_code == 404
        assert tc.delete("/swaps/nope").status_code == 404
        assert tc.post("/swaps/nope/plan").status_code == 404


def test_cancel_queued_pass_marks_cancelled_and_running_interrupts():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/plan")
        passes = tc.post(f"/swaps/{pid}/run", json={"quality": "final", "scene_index": None}).json()["passes"]
        r = tc.post(f"/swaps/{pid}/passes/{passes[0]['id']}/cancel").json()
        assert r["passes"][0]["status"] == "cancelled" and cl.interrupted == 0
        store.update_pass(pid, passes[1]["id"], status="running")
        tc.post(f"/swaps/{pid}/passes/{passes[1]['id']}/cancel")
        assert cl.interrupted == 1 and cl.freed == 1


def test_assemble_lists_missing_passes_then_builds_final_with_audio():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        passes = tc.post(f"/swaps/{pid}/plan").json()["passes"]
        r = tc.post(f"/swaps/{pid}/assemble")
        assert r.status_code == 400 and "scene 1" in r.json()["detail"].lower()
        base = store.project_dir(store.find(pid))
        for p in passes:
            store.update_pass(pid, p["id"], status="done", output_path=_clip(base / "passes" / f"{p['id']}.mp4", 24))
        r = tc.post(f"/swaps/{pid}/assemble")
        assert r.status_code == 200, r.text
        final = r.json()["final"]
        assert final["status"] == "done" and Path(final["path"]).exists()
        assert scenes.count_frames(final["path"]) == 72
        assert "Audio:" in subprocess.run([scenes.ffmpeg_exe(), "-i", final["path"]], capture_output=True, text=True).stderr
        assert r.json()["final_url"].startswith("/swap-media/")


def test_rerun_resets_later_passes_of_the_chunk():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        store.update(pid, lambda pr: pr["scenes"][0]["people"].append({"id": "p3", "cast_id": "c1", "target_description": "the woman", "order": 1}))
        passes = tc.post(f"/swaps/{pid}/plan").json()["passes"]
        first, second = passes[0], passes[1]
        for p in (first, second):
            store.update_pass(pid, p["id"], status="done")
        tc.post(f"/swaps/{pid}/passes/{first['id']}/rerun")
        assert len(js.submitted) == 2
        got = store.find(pid)["passes"]
        assert got[0]["status"] == "queued" and got[1]["status"] == "queued"


def test_characters_endpoint_lists_stubbed_characters_and_delete_works():
    tmp, tc, js, cl, video = _env()
    with tmp:
        assert tc.get("/swap-characters").json()[0]["name"] == "Lafi"
        p = _create(tc, video)
        assert tc.delete(f"/swaps/{p['id']}").status_code == 200
        assert tc.get("/swaps").json() == []


def test_pass_view_exposes_render_parameters_and_source():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        store.update(pid, lambda pr: pr["scenes"][0]["people"].append({"id": "p3", "cast_id": "c1", "target_description": "the woman", "order": 1}))
        passes = tc.post(f"/swaps/{pid}/plan").json()["passes"]
        a, b = passes[0]["params"], passes[1]["params"]
        assert a["steps"] == 20 and a["sampler"] == "res_multistep" and a["turbo"] is False
        assert a["width"] == 96 - 96 % 32 or a["width"] > 0
        assert a["frames_24"] == 24 and a["padded_frames"] == 124 and a["seed"] == 904234
        assert a["source"] == "original footage" and "previous pass" in b["source"]
        assert a["character"] == "Lafi"
        prev = tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0}).json()["passes"][0]["params"]
        assert prev["steps"] == 4 and prev["turbo"] is True and prev["sampler"] == "euler"


def test_run_final_after_a_preview_scene_run_replans_just_that_scene_at_final():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/plan")
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        for p in store.find(pid)["passes"]:
            store.update_pass(pid, p["id"], status="cancelled", job_id=None)
        store.update_pass(pid, store.find(pid)["passes"][1]["id"], status="done", output_path="keep.mp4")
        r = tc.post(f"/swaps/{pid}/run", json={"quality": "final", "scene_index": None}).json()
        first = [p for p in r["passes"] if p["scene_index"] == 0][0]
        assert first["quality"] == "final" and first["status"] == "queued" and first["params"]["steps"] == 20
        later = [p for p in r["passes"] if p["scene_index"] == 2][0]
        assert later["status"] == "done" and later["output_path"] == "keep.mp4"


def test_run_final_rerenders_a_scene_whose_finished_pass_is_only_a_preview():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/plan")
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        first = store.find(pid)["passes"][0]
        store.update_pass(pid, first["id"], status="done", output_path="p.mp4")
        r = tc.post(f"/swaps/{pid}/run", json={"quality": "final", "scene_index": None}).json()
        again = [p for p in r["passes"] if p["scene_index"] == 0][0]
        assert again["quality"] == "final" and again["status"] == "queued"


def test_run_with_size_and_seed_overrides_only_the_passes_it_submits():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/plan")
        r = tc.post(f"/swaps/{pid}/run", json={"quality": "final", "scene_index": 0, "size": 320, "seed": 77}).json()
        a = [p for p in r["passes"] if p["scene_index"] == 0][0]
        b = [p for p in r["passes"] if p["scene_index"] == 2][0]
        assert a["params"]["seed"] == 77
        assert a["params"]["width"] % 32 == 0 and a["params"]["height"] % 32 == 0 and min(a["params"]["width"], a["params"]["height"]) == 320
        assert b["params"]["seed"] == 904234 and b["params"]["width"] != 320


def test_each_scene_gets_its_own_original_clip_with_the_scenes_frame_count():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, d = _setup_project(tc, video)
        got = tc.get(f"/swaps/{pid}").json()
        for s in got["scenes"]:
            assert s["clip_url"] and s["clip_url"].startswith("/swap-media/")
            path = store.ROOT / s["clip_url"][len("/swap-media/"):]
            assert path.exists() and scenes.count_frames(str(path)) == s["frames_24"]
        merged = tc.post(f"/swaps/{pid}/scenes/merge", json={"index": 0}).json()
        first = merged["scenes"][0]
        assert scenes.count_frames(str(store.ROOT / first["clip_url"][len("/swap-media/"):])) == first["frames_24"] == 48


def test_trim_recuts_the_active_result_from_the_full_render():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        base = store.project_dir(store.find(pid))
        raw = _clip(base / "passes" / "raw.mp4", 60)
        out = _clip(base / "passes" / "out.mp4", 24)
        store.update_pass(pid, p["id"], status="done", raw_path=raw, output_path=out, raw_frames=60)
        r = tc.post(f"/swaps/{pid}/passes/{p['id']}/trim", json={"frames": 40})
        assert r.status_code == 200, r.text
        v = [x for x in r.json()["passes"] if x["id"] == p["id"]][0]
        assert scenes.count_frames(out) == 40 and v["params"]["trim_frames"] == 40 and v["params"]["raw_frames"] == 60
        assert tc.post(f"/swaps/{pid}/passes/{p['id']}/trim", json={"frames": 61}).status_code == 400
        assert tc.post(f"/swaps/{pid}/passes/{p['id']}/trim", json={"frames": 0}).status_code == 400
        # trimming again starts from the full render, so it can grow back
        assert tc.post(f"/swaps/{pid}/passes/{p['id']}/trim", json={"frames": 55}).status_code == 200
        assert scenes.count_frames(out) == 55


def test_trim_needs_a_finished_pass():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        assert tc.post(f"/swaps/{pid}/passes/{p['id']}/trim", json={"frames": 10}).status_code == 409


def test_viggle_endpoint_queues_the_pass_with_the_viggle_method():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        r = tc.post(f"/swaps/{pid}/passes/{p['id']}/viggle", json={"size": 320, "seed": 9})
        assert r.status_code == 200, r.text
        v = [x for x in r.json()["passes"] if x["id"] == p["id"]][0]
        assert v["status"] == "queued" and v["params"]["method"] == "viggle" and len(js.submitted) == 1
        assert tc.post(f"/swaps/{pid}/passes/{p['id']}/viggle", json={}).status_code == 409  # already queued
        assert tc.post(f"/swaps/{pid}/passes/nope/viggle", json={}).status_code == 404


def test_a_finished_viggle_pass_renders_in_the_view_and_keeps_its_lora_quality():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p = tc.post(f"/swaps/{pid}/plan").json()["passes"][0]
        out = _clip(store.project_dir(store.find(pid)) / "passes" / "v.mp4", 24)
        store.update_pass(pid, p["id"], status="done", output_path=out, raw_path=out, method="viggle")
        got = tc.get(f"/swaps/{pid}")
        assert got.status_code == 200, got.text
        v = [x for x in got.json()["passes"] if x["id"] == p["id"]][0]
        assert v["params"]["method"] == "viggle" and v["params"]["steps"] == 3 and v["quality"] == "final"


def test_set_cuts_rebuilds_scenes_at_exact_frames_and_keeps_people_of_unchanged_scenes():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        r = tc.put(f"/swaps/{pid}/cuts", json={"cuts": [30, 24, 60, 24]})
        assert r.status_code == 200, r.text
        sc = r.json()["scenes"]
        assert [(s["start_frame_src"], s["end_frame_src"]) for s in sc] == [(0, 23), (24, 29), (30, 59), (60, 71)]
        assert [s["index"] for s in sc] == [0, 1, 2, 3]
        assert [len(s["people"]) for s in sc] == [1, 0, 0, 0]  # only scene 0 kept its exact range, so only it keeps its people
        assert all(s["thumb_url"] and s["clip_url"] for s in sc)
        assert [p["scene_index"] for p in r.json()["passes"]] == [0]  # the scene that kept its person is planned again


def test_set_cuts_rejects_frames_outside_the_video_and_while_running():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        assert tc.put(f"/swaps/{pid}/cuts", json={"cuts": [0]}).status_code == 400
        assert tc.put(f"/swaps/{pid}/cuts", json={"cuts": [72]}).status_code == 400
        tc.post(f"/swaps/{pid}/plan")
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        assert tc.put(f"/swaps/{pid}/cuts", json={"cuts": [10]}).status_code == 409


def test_frame_endpoint_returns_that_frame_as_jpeg():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        white, black = tc.get(f"/swaps/{pid}/frame/23"), tc.get(f"/swaps/{pid}/frame/24")
        assert white.status_code == 200 and white.headers["content-type"] == "image/jpeg"
        import cv2, numpy as np
        mean = lambda r: cv2.imdecode(np.frombuffer(r.content, np.uint8), 0).mean()
        assert mean(white) > 200 and mean(black) < 50  # frame 23 is the last white one, 24 the first black one
        assert tc.get(f"/swaps/{pid}/frame/9999").status_code == 400


def test_scenes_must_be_confirmed_and_changing_the_cuts_unconfirms():
    tmp, tc, js, cl, video = _env()
    with tmp:
        p = _create(tc, video)
        pid = p["id"]
        assert p["scenes_confirmed"] is False
        assert tc.post(f"/swaps/{pid}/detect-scenes").json()["scenes_confirmed"] is False
        assert tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": True}).json()["scenes_confirmed"] is True
        assert tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": False}).json()["scenes_confirmed"] is False
        tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": True})
        assert tc.put(f"/swaps/{pid}/cuts", json={"cuts": [24]}).json()["scenes_confirmed"] is False
        tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": True})
        assert tc.post(f"/swaps/{pid}/detect-scenes").json()["scenes_confirmed"] is False


def test_confirming_needs_scenes_and_unconfirming_is_refused_while_running():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid = _create(tc, video)["id"]
        assert tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": True}).status_code == 400  # nothing split yet
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": True})
        tc.post(f"/swaps/{pid}/plan")
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        assert tc.post(f"/swaps/{pid}/scenes/confirm", json={"confirmed": False}).status_code == 409


def test_projects_made_before_confirmation_existed_count_as_confirmed_when_they_have_work():
    from backend.swap import store as st
    assert st._migrate({"scenes": [{"chunks": []}], "cast": [{"id": "c"}], "passes": []})["scenes_confirmed"] is True
    assert st._migrate({"scenes": [{"chunks": []}], "cast": [], "passes": []})["scenes_confirmed"] is False
    assert st._migrate({"scenes": [], "cast": [], "passes": [], "scenes_confirmed": True})["scenes_confirmed"] is True


def _scene_patch(index, people, background=""):
    return {"index": index, "background_text": background,
            "people": [{"id": pid, "cast_id": cid, "target_description": t, "order": i} for i, (pid, cid, t) in enumerate(people)]}


def _passes_by_scene(view):
    return {p["scene_index"]: p for p in view["passes"]}


def test_saving_a_scene_plans_only_that_scene_and_leaves_the_others_results_alone():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)  # scenes 0 and 2 have a person, so they already have passes
        view = tc.get(f"/swaps/{pid}").json()
        assert sorted(_passes_by_scene(view)) == [0, 2]
        done = _passes_by_scene(view)[2]
        store.update_pass(pid, done["id"], status="done", output_path="x.mp4", seconds=5)
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(0, [("p1", "c1", "the man")], "A plain wall.")]})
        assert r.status_code == 200, r.text
        by = _passes_by_scene(r.json())
        assert by[0]["status"] == "draft" and "A plain wall." in by[0]["prompt"]
        assert by[2]["id"] == done["id"] and by[2]["status"] == "done" and by[2]["output_path"] == "x.mp4"


def test_saving_a_scene_with_nothing_changed_keeps_an_edited_prompt():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        p0 = _passes_by_scene(tc.get(f"/swaps/{pid}").json())[0]
        tc.patch(f"/swaps/{pid}/passes/{p0['id']}", json={"prompt": "my own prompt"})
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(0, [("p1", "c1", "the man")])]})
        assert _passes_by_scene(r.json())[0]["prompt"] == "my own prompt"


def test_a_scene_gets_its_pass_when_a_person_is_added_and_loses_it_when_the_last_is_removed():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(1, [("p9", "c1", "the woman")])]})
        assert sorted(_passes_by_scene(r.json())) == [0, 1, 2]
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(1, [])]})
        assert sorted(_passes_by_scene(r.json())) == [0, 2]
        # a person with no character chosen yet is not planned (no half-filled blocked pass)
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(1, [("p9", None, "the woman")])]})
        assert sorted(_passes_by_scene(r.json())) == [0, 2]


def test_changing_a_cast_entry_refreshes_the_prompts_of_the_scenes_that_use_it():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        cast = [{"id": "c1", "name": "Lafi", "image_path": "lafi.png", "appearance": "a slim woman", "outfit": "a red coat", "body": "slim"}]
        r = tc.patch(f"/swaps/{pid}", json={"cast": cast})
        assert len(r.json()["passes"]) == 2 and all("a red coat" in p["prompt"] for p in r.json()["passes"])


def test_saving_a_scene_is_refused_while_its_pass_is_running():
    tmp, tc, js, cl, video = _env()
    with tmp:
        pid, _ = _setup_project(tc, video)
        tc.post(f"/swaps/{pid}/run", json={"quality": "preview", "scene_index": 0})
        r = tc.patch(f"/swaps/{pid}", json={"scenes": [_scene_patch(0, [("p1", "c1", "someone else")])]})
        assert r.status_code == 409
        assert _passes_by_scene(tc.get(f"/swaps/{pid}").json())[0]["status"] == "queued"


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
