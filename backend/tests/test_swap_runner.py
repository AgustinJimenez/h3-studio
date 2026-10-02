from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from backend.swap import graph, runner, scenes


def _make(path: Path, frames: int, color: str, size: str = "96x160") -> str:
    subprocess.run([scenes.ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=24",
                    "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


class FakeClient:
    def __init__(self, out_bytes: bytes, entry: dict | None = None):
        self.calls: list[tuple] = []
        self.out_bytes = out_bytes
        self.entry = entry
        self.graphs: list[dict] = []

    def ensure_running(self):
        self.calls.append(("ensure_running",))

    def job_started(self):
        self.calls.append(("job_started",))

    def job_finished(self):
        self.calls.append(("job_finished",))

    def free(self):
        self.calls.append(("free",))

    def interrupt(self):
        self.calls.append(("interrupt",))

    def upload(self, path):
        self.calls.append(("upload", Path(path).name))
        return "up_" + Path(path).name

    def queue(self, g):
        self.calls.append(("queue",))
        self.graphs.append(g)
        return "pid1"

    def wait(self, prompt_id):
        self.calls.append(("wait", prompt_id))
        if self.entry is not None:
            return self.entry
        return {"status": {"status_str": "success"},
                "outputs": {graph.SAVE_NODE: {"images": [{"filename": "o.mp4", "subfolder": "h3studio", "type": "output"}]}}}

    def view(self, filename, subfolder, type_):
        self.calls.append(("view", filename))
        return self.out_bytes


def _project(d: Path, src: str, frames: int = 48) -> dict:
    n_pad = scenes.grid_length(frames)
    return {
        "id": "p1", "source": {"path": src, "fps": 24.0},
        "settings": {"width": 96, "height": 160, "seed": 7},
        "cast": [{"id": "c1", "name": "A", "image_path": str(d / "a.png"), "appearance": "a tall man", "outfit": "a red coat", "body": ""},
                 {"id": "c2", "name": "B", "image_path": str(d / "b.png"), "appearance": "a short man", "outfit": "a blue coat", "body": ""}],
        "scenes": [{"index": 0, "start_frame_src": 0, "end_frame_src": frames - 1, "background_text": "",
                    "people": [{"id": "pa", "cast_id": "c1", "target_description": "the man on the left", "order": 0},
                               {"id": "pb", "cast_id": "c2", "target_description": "the man on the right", "order": 1}],
                    "chunks": [{"index": 0, "start": 0, "end": frames - 1, "frames_24": frames, "padded_frames": n_pad}]}],
        "passes": [
            {"id": "pass0000aaaa", "scene_index": 0, "chunk_index": 0, "person_id": "pa", "order": 0, "quality": "final",
             "prompt": "P0", "status": "queued", "raw_path": None},
            {"id": "pass1111bbbb", "scene_index": 0, "chunk_index": 0, "person_id": "pb", "order": 1, "quality": "final",
             "prompt": "P1", "status": "queued", "raw_path": None},
        ],
    }


def _setup(d: Path, color: str = "gray", out_frames: int = 56):
    (d / "a.png").write_bytes(b"x")
    (d / "b.png").write_bytes(b"x")
    src = _make(d / "src.mp4", 48, "white")
    out = Path(_make(d / "fake_out.mp4", out_frames, color)).read_bytes()
    return src, out


def test_first_pass_cuts_source_writes_raw_padded_and_trimmed_output():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        client = FakeClient(out)
        res = runner.run_pass(proj, proj["passes"][0], client, paths={"dir": d / "passes"})
        assert scenes.count_frames(res["raw_path"]) == 56
        assert scenes.count_frames(res["output_path"]) == 48
        assert res["mean_luma"] > 20
        names = [c[1] for c in client.calls if c[0] == "upload"]
        assert len(names) == 2 and names[1] == "a.png"
        g = client.graphs[0]
        assert g["12"]["inputs"]["length"] == 56 and g["12"]["inputs"]["prompt"] == "P0"
        assert g["13"]["inputs"]["noise_seed"] == 7
        assert g[graph.SAVE_NODE]["inputs"]["filename_prefix"] == "h3studio/swap_pass0000"


def test_second_pass_uses_previous_raw_output_as_source():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        prev = _make(d / "prev_raw.mp4", 56, "gray")
        proj["passes"][0].update(status="done", raw_path=prev)
        client = FakeClient(out)
        runner.run_pass(proj, proj["passes"][1], client, paths={"dir": d / "passes"})
        names = [c[1] for c in client.calls if c[0] == "upload"]
        assert names[0] == "prev_raw.mp4" and names[1] == "b.png"


def test_second_pass_fails_when_previous_pass_not_done():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        client = FakeClient(out)
        try:
            runner.run_pass(proj, proj["passes"][1], client, paths={"dir": d / "passes"})
        except runner.PassError as exc:
            assert "previous pass" in str(exc)
            assert not any(c[0] == "queue" for c in client.calls)
        else:
            raise AssertionError("expected PassError")


def test_failed_history_raises_with_exception_message():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        entry = {"status": {"status_str": "error", "messages": [["execution_error", {"exception_message": "OOM boom"}]]}, "outputs": {}}
        try:
            runner.run_pass(proj, proj["passes"][0], FakeClient(out, entry), paths={"dir": d / "passes"})
        except runner.PassError as exc:
            assert "OOM boom" in str(exc)
        else:
            raise AssertionError("expected PassError")


def test_missing_save_node_output_raises():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        entry = {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": "x.png"}]}}}
        try:
            runner.run_pass(proj, proj["passes"][0], FakeClient(out, entry), paths={"dir": d / "passes"})
        except runner.PassError as exc:
            assert "no SaveVideo output" in str(exc)
        else:
            raise AssertionError("expected PassError")


def test_black_output_is_rejected():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d, color="black")
        proj = _project(d, src)
        try:
            runner.run_pass(proj, proj["passes"][0], FakeClient(out), paths={"dir": d / "passes"})
        except runner.PassError as exc:
            assert "black" in str(exc)
        else:
            raise AssertionError("expected PassError")


class FakeStore:
    def __init__(self, proj):
        self.proj = proj

    def find(self, pid):
        return self.proj

    def project_dir(self, proj):
        return Path(self.proj["_dir"])

    def update_pass(self, pid, pass_id, **fields):
        for p in self.proj["passes"]:
            if p["id"] == pass_id:
                p.update(fields)


def test_make_runner_records_done_and_always_frees():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["_dir"] = str(d)
        client = FakeClient(out)
        released: list[int] = []
        r = runner.make_runner("p1", "pass0000aaaa", store_mod=FakeStore(proj), client_factory=lambda: client,
                               release_wangp=lambda: released.append(1))
        result = r(d / "ignored.mp4")
        assert Path(result).exists() and released == [1]
        assert proj["passes"][0]["status"] == "done" and proj["passes"][0]["mean_luma"] > 20
        assert client.calls[0] == ("job_started",) and client.calls[-1] == ("job_finished",) and ("free",) in client.calls


def test_make_runner_failure_records_failed_and_frees():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d, color="black")
        proj = _project(d, src)
        proj["_dir"] = str(d)
        client = FakeClient(out)
        r = runner.make_runner("p1", "pass0000aaaa", store_mod=FakeStore(proj), client_factory=lambda: client,
                               release_wangp=lambda: None)
        try:
            r(d / "x.mp4")
        except runner.PassError:
            pass
        else:
            raise AssertionError("expected PassError")
        assert proj["passes"][0]["status"] == "failed" and "black" in proj["passes"][0]["error"]
        assert ("free",) in client.calls and client.calls[-1] == ("job_finished",)


def test_cancelled_pass_never_touches_comfyui():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["_dir"] = str(d)
        proj["passes"][0]["status"] = "cancelled"
        client = FakeClient(out)
        r = runner.make_runner("p1", "pass0000aaaa", store_mod=FakeStore(proj), client_factory=lambda: client,
                               release_wangp=lambda: None)
        try:
            r(d / "x.mp4")
        except runner.PassError as exc:
            assert "cancelled" in str(exc)
        else:
            raise AssertionError("expected PassError")
        assert client.calls == []


def test_pass_cancelled_while_running_stays_cancelled_when_comfyui_is_interrupted():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["_dir"] = str(d)
        store = FakeStore(proj)

        class Interrupted(FakeClient):
            def wait(self, prompt_id):
                store.update_pass("p1", "pass0000aaaa", status="cancelled")  # what the cancel hook does
                raise RuntimeError("interrupted")

        r = runner.make_runner("p1", "pass0000aaaa", store_mod=store, client_factory=lambda: Interrupted(out), release_wangp=lambda: None)
        try:
            r(d / "x.mp4")
        except runner.PassError:
            pass
        else:
            raise AssertionError("expected PassError")
        assert proj["passes"][0]["status"] == "cancelled"


def test_pass_level_size_and_seed_override_the_project_settings():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["passes"][0].update(width=320, height=320, seed=5)
        client = FakeClient(out)
        runner.run_pass(proj, proj["passes"][0], client, paths={"dir": d / "passes"})
        g = client.graphs[0]
        assert (g["12"]["inputs"]["width"], g["12"]["inputs"]["height"]) == (320, 320) and g["13"]["inputs"]["noise_seed"] == 5


def test_control_pass_uploads_an_edge_video_and_adds_the_control_patch():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        src, out = _setup(d)
        proj = _project(d, src)
        proj["passes"][0]["control"] = {"kind": "canny", "strength": 0.5}
        client = FakeClient(out)
        runner.run_pass(proj, proj["passes"][0], client, paths={"dir": d / "passes"})
        uploads = [c[1] for c in client.calls if c[0] == "upload"]
        assert len(uploads) == 3 and uploads[2].endswith("_edges.mp4")
        g = client.graphs[0]
        assert g["cn"]["inputs"]["strength"] == 0.5 and g["cn_v"]["inputs"]["file"] == "up_" + uploads[2].removeprefix("up_")


def test_lead_in_lengthens_the_render_and_is_cut_off_the_result():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "a.png").write_bytes(b"x")
        (d / "b.png").write_bytes(b"x")
        src = _make(d / "src.mp4", 96, "white")
        out = Path(_make(d / "fake_out.mp4", 130, "gray")).read_bytes()
        proj = _project(d, src, frames=48)
        proj["scenes"][0].update(start_frame_src=48, end_frame_src=95)  # the scene is the second half; 48 frames precede it
        proj["passes"][0]["lead_frames"] = 8
        client = FakeClient(out)
        res = runner.run_pass(proj, proj["passes"][0], client, paths={"dir": d / "passes"})
        assert res["lead_used"] == 8
        assert client.graphs[0]["12"]["inputs"]["length"] == scenes.render_length(8 + 48) == 124
        assert scenes.count_frames(res["output_path"]) == 48 and scenes.count_frames(res["raw_path"]) == 130


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
