"""Generation job tracking, ported from shared/mcp_server.py's _JobRecord /
_JobStore pattern, extended into a real FIFO queue: WanGPSession only runs
one job at a time, so instead of rejecting a second submit() with a 409,
JobStore accepts it immediately (status -> "queued") and starts it the
moment the previous job finishes (status -> "running"). Generic over what's
being generated (a clip, a character's reference video, ...) — the caller
supplies the destination path and what to do with the result."""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable


class _JobRecord:
    def __init__(self, job_id: str, job: Any, dest_path: Path, on_done: Callable[..., None]) -> None:
        self.job_id = job_id
        self.job = job
        self.dest_path = dest_path
        self.on_done = on_done
        self.created_at = time.time()
        self._watcher = threading.Thread(target=self._watch, daemon=True, name=f"job-{job_id}")

    def start(self) -> None:
        self._watcher.start()

    def _watch(self) -> None:
        for _ in self.job.events.iter(timeout=0.2):
            pass  # events are ignored for now; only the final result matters
        self._finalize()

    def _finalize(self) -> None:
        duration_seconds = round(time.time() - self.created_at, 1)
        try:
            result = self.job.result(timeout=0)
        except Exception as exc:  # pragma: no cover - defensive
            self.on_done(status="failed", output_path=None, error=str(exc), duration_seconds=duration_seconds)
            return

        if result.success and result.generated_files:
            # WanGP always writes into the session-wide staging output_dir;
            # move the finished file into its real destination.
            src_path = Path(result.generated_files[0])
            self.dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(self.dest_path))
            self.on_done(status="done", output_path=str(self.dest_path), error=None, duration_seconds=duration_seconds)
        else:
            message = "; ".join(error.message for error in result.errors) or "generation failed"
            self.on_done(status="failed", output_path=None, error=message, duration_seconds=duration_seconds)


class _PendingItem:
    def __init__(self, job_id: str, settings: dict[str, Any], dest_path: Path, on_done: Callable[..., None], on_running: Callable[[], None] | None) -> None:
        self.job_id = job_id
        self.settings = settings
        self.dest_path = dest_path
        self.on_done = on_done
        self.on_running = on_running


class JobStore:
    """A FIFO queue in front of the one WanGPSession job slot. submit() always
    accepts and returns a job_id right away; the item runs immediately if the
    session is idle, otherwise it waits in line and starts automatically as
    soon as the current job's watcher thread calls _finalize()."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._jobs: dict[str, _JobRecord] = {}
        self._active_job_id: str | None = None
        self._pending: deque[_PendingItem] = deque()
        self._lock = threading.RLock()

    def is_busy(self) -> bool:
        with self._lock:
            if self._active_job_id is None:
                return False
            record = self._jobs.get(self._active_job_id)
            return record is not None and not record.job.done

    def queue_length(self) -> int:
        with self._lock:
            return len(self._pending)

    def submit(
        self,
        settings: dict[str, Any],
        dest_path: Any,
        on_done: Callable[..., None],
        on_queued: Callable[[str], None] | None = None,
        on_running: Callable[[], None] | None = None,
    ) -> str:
        """Always accepts. on_queued(job_id) runs synchronously before this
        call returns, so the caller can record the job_id/status='queued'
        without racing a job that starts (or even finishes) immediately.
        on_running() fires right before the item is actually handed to
        WanGP (status -> 'running'). on_done(status=..., output_path=...,
        error=...) fires from a background thread once it finishes."""
        job_id = uuid.uuid4().hex
        item = _PendingItem(job_id, settings, dest_path, on_done, on_running)
        with self._lock:
            self._pending.append(item)
            if on_queued is not None:
                on_queued(job_id)
            self._maybe_start_next()
        return job_id

    def _maybe_start_next(self) -> None:
        """Caller must hold self._lock."""
        if self.is_busy() or not self._pending:
            return
        item = self._pending.popleft()
        job = self._session.submit_task(item.settings)
        record = _JobRecord(item.job_id, job, item.dest_path, self._on_item_done(item))
        self._jobs[item.job_id] = record
        self._active_job_id = item.job_id
        if item.on_running is not None:
            item.on_running()
        record.start()

    def _on_item_done(self, item: _PendingItem) -> Callable[..., None]:
        def _wrapped(**kwargs: Any) -> None:
            item.on_done(**kwargs)
            with self._lock:
                self._active_job_id = None
                self._maybe_start_next()

        return _wrapped

    def get(self, job_id: str) -> _JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)
