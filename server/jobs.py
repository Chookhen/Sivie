"""In-process background job runner for the detection pipeline.

The website's Processing page kicks off ``main.py`` as a subprocess so the heavy
YOLO/Gemini imports never block the API event loop. Each job captures combined
stdout/stderr line-by-line; the frontend polls ``/api/process/{id}`` and streams
new log lines using the returned ``next_offset`` cursor.

Only one pipeline job runs at a time (the work is CPU/GPU heavy), which also keeps
the demo predictable.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_LOG_LINES = 4000


class Job:
    def __init__(self, job_id: str, label: str) -> None:
        self.id = job_id
        self.label = label
        self.status = "running"  # running | done | error
        self.log: List[str] = []
        self.returncode: Optional[int] = None
        self.error: Optional[str] = None
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self.log.append(line)
            extra = len(self.log) - MAX_LOG_LINES
            if extra > 0:
                del self.log[:extra]

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            total = len(self.log)
            lines = self.log[since:] if since < total else []
            status, rc, err = self.status, self.returncode, self.error
            started, ended = self.started_at, self.ended_at
        return {
            "id": self.id,
            "label": self.label,
            "status": status,
            "returncode": rc,
            "error": err,
            "started_at": started,
            "ended_at": ended,
            "elapsed_sec": round((ended or time.time()) - started, 1),
            "log": lines,
            "next_offset": total,
        }


_JOBS: Dict[str, Job] = {}
_ACTIVE: Optional[str] = None
_LOCK = threading.Lock()


def get_job(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def active_job() -> Optional[Job]:
    with _LOCK:
        if _ACTIVE and _ACTIVE in _JOBS and _JOBS[_ACTIVE].status == "running":
            return _JOBS[_ACTIVE]
    return None


def start_job(
    cmd: List[str],
    label: str,
    on_success: Optional[Callable[[], Optional[str]]] = None,
    env: Optional[dict] = None,
) -> Job:
    """Spawn ``cmd`` in a background thread and stream its output into a Job."""
    global _ACTIVE
    with _LOCK:
        if _ACTIVE and _ACTIVE in _JOBS and _JOBS[_ACTIVE].status == "running":
            raise RuntimeError("A processing job is already running.")
        job = Job(uuid.uuid4().hex[:12], label)
        _JOBS[job.id] = job
        _ACTIVE = job.id

    def run() -> None:
        job.append(f"$ {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                env=env or os.environ.copy(),
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                job.append(line.rstrip("\n"))
            proc.wait()
            job.returncode = proc.returncode
            if proc.returncode == 0:
                if on_success is not None:
                    try:
                        msg = on_success()
                        if msg:
                            job.append(msg)
                    except Exception as exc:  # noqa: BLE001
                        job.append(f"[post] WARN {exc}")
                job.status = "done"
            else:
                job.status = "error"
                job.error = f"pipeline exited with code {proc.returncode}"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            job.append(f"[error] {exc}")
        finally:
            job.ended_at = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job
