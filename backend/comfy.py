"""ComfyUI as an alternative Qwen-Image 2.1 provider for character images.

Why: WanGP's native Qwen 2.1 integration produced broken (crusty) edits and was
2-4x slower in a controlled A/B on 2026-09-23 — same source/prompt/seed, with
and without the LoRA — while ComfyUI's GGUF path was clean at both CFG 1 and 4.

The graph mirrors what was proven by hand: UnetLoaderGGUF (+ optional
LoraLoaderModelOnly) -> TextEncodeQwenImage21 (edit sources wired as
`images.image_N`, which also yields the edit latent) -> KSampler -> VAEDecode.
Everything runs through the JobStore's single slot (submit_callable), and the
WanGP model is released first / ComfyUI's memory freed after, so the two never
hold the 23GB card at the same time.
"""

from __future__ import annotations

import json
import mimetypes
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

import psutil

COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFY_ROOT = Path(os.environ.get("COMFYUI_ROOT", r"E:\repo\ComfyUI_windows_portable\ComfyUI"))
# Portable install used to auto-start ComfyUI headless when a job needs it.
COMFY_PORTABLE = Path(os.environ.get("COMFYUI_PORTABLE", str(COMFY_ROOT.parent)))
COMFY_PYTHON = COMFY_PORTABLE / "python_embeded" / "python.exe"
# Only a ComfyUI that h3-studio started itself is ever shut down for idling.
IDLE_SHUTDOWN_S = float(os.environ.get("COMFYUI_IDLE_MINUTES", "15")) * 60
STARTUP_TIMEOUT_S = 240
LOG_PATH = Path(__file__).resolve().parent / "data" / "comfyui_autostart.log"
PID_PATH = Path(__file__).resolve().parent / "data" / "comfyui_autostart.pid"

UNET_NAME = "Qwen-Image-2.1-Q4_K_M-HQv3.gguf"
CLIP_NAME = "qwen3vl_8b_w4a8.safetensors"
VAE_NAME = "qwen_image_2.1_vae_bf16.safetensors"
# ComfyUI's Qwen 2.1 template values; CFG 4 / 40 steps looked the same in the
# A/B but took ~2x longer.
DEFAULT_STEPS = 25
DEFAULT_CFG = 1.0


class ComfyError(RuntimeError):
    pass


def _get(path: str, timeout: float = 10) -> Any:
    with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _post_json(path: str, body: dict[str, Any], timeout: float = 30) -> Any:
    req = urllib.request.Request(f"{COMFY_URL}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise ComfyError(f"ComfyUI {path} -> HTTP {exc.code}: {exc.read().decode(errors='replace')[:1500]}") from exc


def is_available() -> bool:
    try:
        _get("/system_stats", timeout=2)
        return True
    except Exception:
        return False


def _port_open() -> bool:
    """True if something is listening on ComfyUI's port -- i.e. it's running
    but momentarily not answering HTTP (e.g. mid /free)."""
    parsed = urllib.parse.urlparse(COMFY_URL)
    try:
        with socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=1):
            return True
    except OSError:
        return False


def can_autostart() -> bool:
    return COMFY_PYTHON.is_file() and (COMFY_ROOT / "main.py").is_file()


class _Manager:
    """Starts ComfyUI headless on demand and stops it after IDLE_SHUTDOWN_S
    without jobs -- but only an instance it started itself; a ComfyUI the user
    launched by hand is used as-is and never touched.

    Ownership survives backend restarts: the auto-started process id is kept
    in PID_PATH and re-adopted on startup (adopt()), so a force-killed
    backend doesn't leave an orphaned ComfyUI that nothing ever idles out."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: psutil.Process | None = None
        self._busy = 0
        self._last_used = time.time()
        self._watcher: threading.Thread | None = None

    def _alive(self) -> bool:
        try:
            return self._proc is not None and self._proc.is_running() and self._proc.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    def owns_running_instance(self) -> bool:
        with self._lock:
            return self._alive()

    def adopt(self) -> None:
        """Called at backend startup: take back ownership of a ComfyUI this
        app auto-started before a restart. The command line is checked so a
        reused pid can never make us kill an unrelated process."""
        with self._lock:
            try:
                pid = int(PID_PATH.read_text().strip())
                proc = psutil.Process(pid)
                cmdline = " ".join(proc.cmdline())
            except (OSError, ValueError, psutil.Error):
                PID_PATH.unlink(missing_ok=True)
                return
            if "main.py" not in cmdline or "--disable-auto-launch" not in cmdline or str(COMFY_ROOT) not in cmdline:
                PID_PATH.unlink(missing_ok=True)
                return
            self._proc = proc
            self._last_used = time.time()
            self._start_watcher()

    def ensure_running(self) -> None:
        deadline = time.time() + STARTUP_TIMEOUT_S
        # Already up, or up but briefly unresponsive (mid /free): wait for it.
        while not is_available():
            with self._lock:
                if not self._alive() and not _port_open():
                    self._start()
                if not self._alive():
                    raise ComfyError(f"ComfyUI exited while starting -- see {LOG_PATH}")
            if time.time() > deadline:
                raise ComfyError(f"ComfyUI did not come up at {COMFY_URL} within {STARTUP_TIMEOUT_S}s -- see {LOG_PATH}")
            time.sleep(2)

    def _start(self) -> None:
        if not can_autostart():
            raise ComfyError(f"ComfyUI is not running at {COMFY_URL} and no portable install was found at {COMFY_PORTABLE} to start it.")
        port = urllib.parse.urlparse(COMFY_URL).port or 8188
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log = open(LOG_PATH, "ab")
        self._proc = psutil.Popen(
            [str(COMFY_PYTHON), "-s", str(COMFY_ROOT / "main.py"), "--windows-standalone-build", "--disable-auto-launch", "--port", str(port)],
            cwd=str(COMFY_PORTABLE), stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        PID_PATH.write_text(str(self._proc.pid))
        self._last_used = time.time()
        self._start_watcher()

    def _start_watcher(self) -> None:
        if self._watcher is None or not self._watcher.is_alive():
            self._watcher = threading.Thread(target=self._idle_loop, daemon=True, name="comfyui-idle")
            self._watcher.start()

    def job_started(self) -> None:
        with self._lock:
            self._busy += 1
            self._last_used = time.time()

    def job_finished(self) -> None:
        with self._lock:
            self._busy = max(0, self._busy - 1)
            self._last_used = time.time()

    def _idle_loop(self) -> None:
        while True:
            time.sleep(30)
            with self._lock:
                if not self._alive():
                    self._proc = None
                    PID_PATH.unlink(missing_ok=True)
                    return
                if self._busy == 0 and time.time() - self._last_used > IDLE_SHUTDOWN_S:
                    self.stop()
                    return

    def stop(self) -> None:
        with self._lock:
            if self._alive():
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=20)
                except psutil.TimeoutExpired:
                    self._proc.kill()
                except psutil.Error:
                    pass
            self._proc = None
            PID_PATH.unlink(missing_ok=True)


manager = _Manager()


def list_loras() -> list[str]:
    """LoRA files ComfyUI can load. Read from disk so the dropdown works even
    while ComfyUI is stopped (a generation then fails with a clear message)."""
    folder = COMFY_ROOT / "models" / "loras"
    if not folder.is_dir():
        return []
    names = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.safetensors"))
    # The folder mixes LoRAs for every model ComfyUI runs; only Qwen ones apply
    # here (character LoRAs are named <name>_qwen21_e<N>). Fall back to all.
    qwen = [n for n in names if "qwen" in n.lower()]
    return qwen or names


def _upload_image(path: str) -> str:
    """Uploads a local file to ComfyUI's input folder, returns the name to use in LoadImage."""
    src = Path(path)
    boundary = uuid.uuid4().hex
    name = f"h3studio_{uuid.uuid4().hex[:8]}{src.suffix.lower()}"
    content_type = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
        src.read_bytes(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(f"{COMFY_URL}/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        info = json.loads(r.read())
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def build_graph(params: dict[str, Any], uploaded_sources: list[str]) -> dict[str, Any]:
    g: dict[str, Any] = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET_NAME}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_NAME, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": params["output_prefix"]}},
    }
    encode: dict[str, Any] = {"clip": ["2", 0], "prompt": params["prompt"], "negative_prompt": "", "resolution": 1024}
    if uploaded_sources:
        encode["vae"] = ["3", 0]
        for i, name in enumerate(uploaded_sources, start=1):
            g[f"src{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
            encode[f"images.image_{i}"] = [f"src{i}", 0]
        latent = ["5", 2]  # TextEncodeQwenImage21 emits the edit latent when given images
    else:
        g["6"] = {"class_type": "EmptyLatentImage", "inputs": {"width": params["width"], "height": params["height"], "batch_size": 1}}
        latent = ["6", 0]
    g["5"] = {"class_type": "TextEncodeQwenImage21", "inputs": encode}

    model: list[Any] = ["1", 0]
    if params.get("lora"):
        g["10"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": params["lora"], "strength_model": float(params.get("lora_multiplier", 1.0))}}
        model = ["10", 0]
    g["7"] = {"class_type": "KSampler", "inputs": {
        "model": model, "positive": ["5", 0], "negative": ["5", 1], "latent_image": latent,
        "seed": int(params["seed"]), "steps": int(params.get("steps", DEFAULT_STEPS)), "cfg": float(params.get("cfg", DEFAULT_CFG)),
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1,
    }}
    return g


def make_runner(params: dict[str, Any], release_wangp: Callable[[], None], timeout_s: float = 1800) -> Callable[[Path], Path]:
    """Returns a JobStore.submit_callable runner that generates one image and
    writes it to dest_path (suffix taken from ComfyUI's output file)."""

    def run(dest_path: Path) -> Path:
        release_wangp()  # free WanGP's VRAM before ComfyUI (re)starts / loads Qwen
        manager.job_started()
        try:
            manager.ensure_running()
            uploaded = [_upload_image(p) for p in params.get("source_paths") or []]
            prompt_id = _post_json("/prompt", {"prompt": build_graph(params, uploaded)})["prompt_id"]
            deadline = time.time() + timeout_s
            while True:
                history = _get(f"/history/{prompt_id}")
                if prompt_id in history:
                    entry = history[prompt_id]
                    break
                if time.time() > deadline:
                    raise ComfyError("ComfyUI generation timed out")
                time.sleep(1.5)
            status = entry.get("status") or {}
            if status.get("status_str") != "success":
                messages = [m for m in status.get("messages") or [] if m and m[0] == "execution_error"]
                detail = messages[0][1].get("exception_message") if messages else status.get("status_str")
                raise ComfyError(f"ComfyUI execution failed: {detail}")
            images = [img for out in entry.get("outputs", {}).values() for img in out.get("images", [])]
            if not images:
                raise ComfyError("ComfyUI finished but produced no image")
            img = images[0]
            query = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
            with urllib.request.urlopen(f"{COMFY_URL}/view?{query}", timeout=60) as r:
                data = r.read()
            if not dest_path.suffix:
                dest_path = dest_path.with_suffix(Path(img["filename"]).suffix or ".png")
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)
            return dest_path
        finally:
            # Give the VRAM back so the next H3 clip doesn't crawl.
            try:
                _post_json("/free", {"unload_models": True, "free_memory": True}, timeout=30)
            except Exception:
                pass
            manager.job_finished()

    return run
