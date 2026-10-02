"""Runs one swap pass (one person, one chunk of one scene) through ComfyUI as a queued job."""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import graph, progress, scenes

BLACK_LUMA = 20.0  # video-range black is 16; real footage is far above 20
POLL_S = 1.5
TIMEOUT_S = 3 * 3600


class PassError(RuntimeError):
    pass


class ComfyClient:
    """The slice of ComfyUI the runner needs, over backend.comfy. Tests replace it with a fake."""

    def __init__(self, timeout_s: float = TIMEOUT_S) -> None:
        from .. import comfy
        self._c = comfy
        self._timeout_s = timeout_s
        self._client_id = uuid.uuid4().hex
        self._listening = threading.Event()
        self.on_progress: Callable[[dict[str, Any]], None] | None = None

    def ensure_running(self) -> None:
        self._c.manager.ensure_running()

    def job_started(self) -> None:
        self._c.manager.job_started()

    def job_finished(self) -> None:
        self._c.manager.job_finished()

    def upload(self, path: str) -> str:
        return self._c._upload_image(str(path))

    def queue(self, g: dict[str, Any]) -> str:
        prompt_id = self._c._post_json("/prompt", {"prompt": g, "client_id": self._client_id})["prompt_id"]
        threading.Thread(target=self._listen, args=(prompt_id,), daemon=True, name=f"comfy-progress-{prompt_id[:6]}").start()
        return prompt_id

    def _listen(self, prompt_id: str) -> None:
        """Forwards ComfyUI's websocket progress for this prompt to on_progress until the pass is over."""
        try:
            import websocket  # websocket-client
            ws = websocket.create_connection(self._c.COMFY_URL.replace("http", "ws", 1) + f"/ws?clientId={self._client_id}", timeout=5)
        except Exception:  # noqa: BLE001 - progress is a nicety; the pass runs without it
            return
        self._listening.set()
        try:
            while self._listening.is_set():
                try:
                    raw = ws.recv()
                except Exception as exc:  # noqa: BLE001
                    if type(exc).__name__ == "WebSocketTimeoutException":
                        continue
                    return
                if not isinstance(raw, str) or self.on_progress is None:
                    continue
                try:
                    info = progress.from_message(json.loads(raw), prompt_id)
                except ValueError:
                    continue
                if info:
                    self.on_progress(info)
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def stop_listening(self) -> None:
        self._listening.clear()

    def wait(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.time() + self._timeout_s
        while True:
            history = self._c._get(f"/history/{prompt_id}")
            if prompt_id in history:
                return history[prompt_id]
            if time.time() > deadline:
                raise PassError("ComfyUI generation timed out")
            time.sleep(POLL_S)

    def view(self, filename: str, subfolder: str, type_: str) -> bytes:
        query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type_})
        with urllib.request.urlopen(f"{self._c.COMFY_URL}/view?{query}", timeout=120) as r:
            return r.read()

    def free(self) -> None:
        try:
            self._c._post_json("/free", {"unload_models": True, "free_memory": True}, timeout=30)
        except Exception:  # noqa: BLE001
            pass

    def interrupt(self) -> None:
        try:
            self._c._post_json("/interrupt", {}, timeout=10)
        except Exception:  # noqa: BLE001
            pass


def mean_luma(path: str) -> float:
    """Mean Y of every 8th frame (video-range: black is 16)."""
    r = subprocess.run([scenes.ffmpeg_exe(), "-v", "info", "-i", str(path), "-vf",
                        "select='not(mod(n\\,8))',signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    vals = [float(v) for v in re.findall(r"YAVG=([0-9.]+)", r.stderr)]
    if not vals:
        raise PassError(f"could not measure brightness: {r.stderr[-200:]}")
    return sum(vals) / len(vals)


def _find(items: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any]:
    for it in items:
        if it.get(key) == value:
            return it
    raise PassError(f"{key} {value!r} not found in the project")


def run_pass(project: dict[str, Any], pass_: dict[str, Any], client: Any, *, paths: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    scene = _find(project["scenes"], "index", pass_["scene_index"])
    chunk = _find(scene["chunks"], "index", pass_["chunk_index"])
    person = _find(scene["people"], "id", pass_["person_id"])
    entry = _find(project["cast"], "id", person["cast_id"])
    out_dir = Path(paths["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]  # every run keeps its own files: re-runs no longer overwrite earlier results
    raw_path = out_dir / f"{pass_['id']}_{run_id}_raw.mp4"
    output_path = out_dir / f"{pass_['id']}_{run_id}.mp4"

    lead_used = 0
    length = chunk["padded_frames"]
    if pass_["order"] == 0:
        source = out_dir / f"{pass_['id']}_src.mp4"
        lead = int(pass_.get("lead_frames") or 0)
        length = scenes.render_length(lead + chunk["frames_24"]) if lead else chunk["padded_frames"]
        lead_used = scenes.extract_segment(project["source"]["path"], str(source), scene["start_frame_src"], scene["end_frame_src"],
                                           float(project["source"]["fps"]), chunk["start"], chunk["end"], length, extend=True, lead=lead)
    else:
        prev = next((p for p in project["passes"] if p["scene_index"] == pass_["scene_index"]
                     and p["chunk_index"] == pass_["chunk_index"] and p["order"] == pass_["order"] - 1), None)
        if prev is None or prev.get("status") != "done" or not prev.get("raw_path"):
            raise PassError("the previous pass of this scene is not done yet")
        source = Path(prev["raw_path"])
        lead_used = int(prev.get("lead_used") or 0)  # the previous pass's render carries the same lead-in
        length = int(prev.get("raw_frames") or 0) + lead_used or chunk["padded_frames"]

    video_name = client.upload(str(source))
    image_name = client.upload(entry["image_path"])
    control = None
    if pass_.get("control"):
        edges = out_dir / f"{pass_['id']}_{run_id}_edges.mp4"
        scenes.make_edge_video(str(source), str(edges))
        control = {"patch": graph.CONTROL_PATCH, "strength": pass_["control"].get("strength", 0.5), "video": client.upload(str(edges))}
    g = graph.build_graph(video_name=video_name, image_name=image_name, prompt=pass_["prompt"],
                          width=pass_.get("width") or project["settings"]["width"], height=pass_.get("height") or project["settings"]["height"],
                          length=length, seed=int(pass_.get("seed") or project["settings"]["seed"]),
                          quality=pass_["quality"], prefix=f"h3studio/swap_{pass_['id'][:8]}",
                          extra_loras=[tuple(x) for x in pass_.get("extra_loras") or []], control=control)
    prompt_id = client.queue(g)
    history = client.wait(prompt_id)
    status = history.get("status") or {}
    if status.get("status_str") != "success":
        messages = [m for m in status.get("messages") or [] if m and m[0] == "execution_error"]
        detail = messages[0][1].get("exception_message") if messages else status.get("status_str")
        raise PassError(f"ComfyUI execution failed: {detail}")
    node = (history.get("outputs") or {}).get(graph.SAVE_NODE) or {}
    files = node.get("images") or node.get("videos") or node.get("gifs") or []
    if not files:
        raise PassError("no SaveVideo output")
    f = files[0]
    raw_path.write_bytes(client.view(f["filename"], f.get("subfolder", ""), f.get("type", "output")))

    luma = mean_luma(str(raw_path))
    if luma < BLACK_LUMA:
        raise PassError(f"black output (mean luma {luma:.1f})")
    try:
        scenes.cut_frames(str(raw_path), str(output_path), lead_used, chunk["frames_24"])
    except RuntimeError as exc:
        raise PassError(f"trimming failed: {exc}") from exc
    return {"run_id": run_id, "output_path": str(output_path), "raw_path": str(raw_path), "mean_luma": round(luma, 1),
            "seconds": round(time.time() - t0, 1), "raw_frames": length - lead_used, "lead_used": lead_used, "quality": pass_["quality"], "width": g["12"]["inputs"]["width"],
            "height": g["12"]["inputs"]["height"], "seed": g["13"]["inputs"]["noise_seed"], "prompt": pass_["prompt"],
            "extra_loras": [list(x) for x in pass_.get("extra_loras") or []], "control": pass_.get("control")}


def make_runner(project_id: str, pass_id: str, *, store_mod: Any, client_factory: Callable[[], Any],
                release_wangp: Callable[[], None]) -> Callable[[Path], Path]:
    def run(_dest: Path) -> Path:
        project = store_mod.find(project_id)
        pass_ = _find(project["passes"], "id", pass_id)
        if pass_.get("status") == "cancelled":
            raise PassError("cancelled")
        store_mod.update_pass(project_id, pass_id, status="running", error=None, started_at=time.time())
        client = client_factory()
        client.on_progress = lambda info: progress.set(pass_id, info)
        release_wangp()  # free WanGP's VRAM before ComfyUI loads H3
        client.job_started()
        try:
            client.ensure_running()
            result = run_pass(project, pass_, client, paths={"dir": Path(store_mod.project_dir(project)) / "passes"})
        except Exception as exc:  # noqa: BLE001
            current = next((p for p in store_mod.find(project_id)["passes"] if p["id"] == pass_id), {})
            if current.get("status") != "cancelled":  # a user cancel interrupts ComfyUI, which surfaces here as an error
                store_mod.update_pass(project_id, pass_id, status="failed", error=str(exc))
            raise exc if isinstance(exc, PassError) else PassError(str(exc)) from exc
        finally:
            progress.clear(pass_id)
            stop = getattr(client, "stop_listening", None)
            if stop:
                stop()
            try:
                client.free()
            finally:
                client.job_finished()
        entry = {"id": result["run_id"], "created_at": time.time(), **{k: result[k] for k in (
            "quality", "width", "height", "seed", "seconds", "mean_luma", "output_path", "raw_path", "prompt", "extra_loras", "control", "raw_frames", "lead_used")}}
        history = list(next((p for p in store_mod.find(project_id)["passes"] if p["id"] == pass_id), {}).get("history") or []) + [entry]
        store_mod.update_pass(project_id, pass_id, status="done", error=None, history=history, output_path=result["output_path"],
                              raw_path=result["raw_path"], mean_luma=result["mean_luma"], seconds=result["seconds"],
                              raw_frames=result.get("raw_frames"), lead_used=result.get("lead_used", 0), trim_frames=None)
        return Path(result["output_path"])

    return run
