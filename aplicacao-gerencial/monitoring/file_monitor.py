from __future__ import annotations

import threading
import time


class FileMonitor:
    def __init__(self, service, interval_seconds: int = 30) -> None:
        self.service = service
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            for negociador in self.service.list_negociadores():
                try:
                    self.service.refresh_negociador(negociador["id"], force=False)
                except Exception:
                    pass
            self._stop.wait(self.interval_seconds)

