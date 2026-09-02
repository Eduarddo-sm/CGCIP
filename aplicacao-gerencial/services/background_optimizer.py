from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable

from services.colchao_service import ColchaoService
from services.parecer_service import ParecerService
from services.protocolo_service import ProtocoloService


class BackgroundOptimizer:
    def __init__(self, parecer: ParecerService, colchao: ColchaoService, protocolo: ProtocoloService | None = None) -> None:
        self.parecer = parecer
        self.colchao = colchao
        self.protocolo = protocolo
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "jobs": {name: dict(job) for name, job in self._jobs.items()},
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

    def refresh_all(self) -> dict[str, Any]:
        scheduled = [
            self._schedule("parecer", self._warm_parecer),
            self._schedule("protocolo", self._warm_protocolo) if self.protocolo else None,
            self._schedule("colchao_alpha", lambda: self._warm_colchao("alpha")),
            self._schedule("colchao_beta", lambda: self._warm_colchao("beta")),
        ]
        return {"ok": True, "scheduled": [name for name in scheduled if name]}

    def refresh_parecer(self) -> dict[str, Any]:
        return {"ok": True, "scheduled": [self._schedule("parecer", self._warm_parecer)]}

    def refresh_colchao(self, profile: str = "alpha") -> dict[str, Any]:
        name = f"colchao_{profile or 'alpha'}"
        return {"ok": True, "scheduled": [self._schedule(name, lambda: self._warm_colchao(profile))]}

    def _schedule(self, name: str, action: Callable[[], dict[str, Any]]) -> str | None:
        with self._lock:
            current = self._jobs.get(name)
            if current and current.get("running"):
                return None
            self._jobs[name] = {
                **(current or {}),
                "name": name,
                "running": True,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "error": "",
            }
        thread = threading.Thread(target=self._run, args=(name, action), daemon=True)
        thread.start()
        return name

    def _run(self, name: str, action: Callable[[], dict[str, Any]]) -> None:
        started = time.perf_counter()
        try:
            result = action()
            with self._lock:
                self._jobs[name] = {
                    **self._jobs.get(name, {}),
                    "running": False,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "result": result,
                    "error": "",
                }
        except Exception as exc:
            with self._lock:
                self._jobs[name] = {
                    **self._jobs.get(name, {}),
                    "running": False,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "error": str(exc),
                }

    def _warm_parecer(self) -> dict[str, Any]:
        return self.parecer.refresh_cache()

    def _warm_protocolo(self) -> dict[str, Any]:
        if not self.protocolo:
            return {"records": 0}
        records = self.protocolo.records()
        return {"records": len(records)}

    def _warm_colchao(self, profile: str) -> dict[str, Any]:
        dashboard = self.colchao.dashboard(profile)
        pendencias = self.colchao.pendencias(profile)
        config = self.colchao.get_profile_config(profile)
        sheets = config.get("sheet_options") or [config.get("main_sheet", "")]
        for sheet_name in sheets:
            self.colchao.query_records(page=1, page_size=100, profile=profile, sheet_name=sheet_name)
        return {
            "dashboard_updated_at": dashboard.get("updated_at"),
            "pendencias": len(pendencias),
            "sheets": [sheet for sheet in sheets if sheet],
        }
