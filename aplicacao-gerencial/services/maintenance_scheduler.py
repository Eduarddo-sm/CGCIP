from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


logger = logging.getLogger("gerencial.maintenance")


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    interval_seconds: int
    initial_delay_seconds: int
    action: Callable[[], dict[str, Any]]


class MaintenanceScheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._status: dict[str, dict[str, Any]] = {}
        self._threads: list[threading.Thread] = []

    def add_job(self, job: ScheduledJob) -> None:
        interval = max(60, int(job.interval_seconds))
        normalized = ScheduledJob(job.name, interval, max(0, int(job.initial_delay_seconds)), job.action)
        with self._lock:
            if normalized.name in self._status:
                raise ValueError(f"Tarefa ja cadastrada: {normalized.name}")
            self._status[normalized.name] = {
                "name": normalized.name,
                "running": False,
                "interval_seconds": normalized.interval_seconds,
                "next_run_in_seconds": normalized.initial_delay_seconds,
            }
        thread = threading.Thread(target=self._loop, args=(normalized,), daemon=True, name=f"maintenance-{normalized.name}")
        self._threads.append(thread)
        thread.start()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"jobs": {name: dict(value) for name, value in self._status.items()}}

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)

    def _loop(self, job: ScheduledJob) -> None:
        if self._wait(job.name, job.initial_delay_seconds):
            return
        while not self._stop.is_set():
            self._run(job)
            if self._wait(job.name, job.interval_seconds):
                return

    def _wait(self, name: str, seconds: int) -> bool:
        deadline = time.monotonic() + seconds
        while not self._stop.is_set():
            remaining = max(0, deadline - time.monotonic())
            with self._lock:
                self._status[name]["next_run_in_seconds"] = int(remaining)
            if remaining <= 0:
                return False
            if self._stop.wait(min(remaining, 30)):
                return True
        return True

    def _run(self, job: ScheduledJob) -> None:
        started = time.perf_counter()
        with self._lock:
            self._status[job.name].update({
                "running": True,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "error": "",
            })
        try:
            result = job.action()
            outcome = {"result": result, "error": ""}
            logger.info("maintenance_completed", extra={"request_id": job.name, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        except Exception as exc:
            outcome = {"result": None, "error": str(exc)}
            logger.exception("maintenance_failed", extra={"request_id": job.name})
        with self._lock:
            self._status[job.name].update({
                "running": False,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "next_run_in_seconds": job.interval_seconds,
                **outcome,
            })
