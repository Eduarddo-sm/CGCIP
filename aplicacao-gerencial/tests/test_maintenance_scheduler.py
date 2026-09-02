from __future__ import annotations

import unittest
import logging

from services.maintenance_scheduler import MaintenanceScheduler, ScheduledJob


class MaintenanceSchedulerTestCase(unittest.TestCase):
    def test_job_records_success_without_leaking_exception(self) -> None:
        scheduler = MaintenanceScheduler()
        job = ScheduledJob("backup", 3600, 0, lambda: {"ok": True})
        scheduler._status[job.name] = {"name": job.name, "running": False}
        scheduler._run(job)
        status = scheduler.status()["jobs"]["backup"]
        self.assertFalse(status["running"])
        self.assertEqual(status["result"], {"ok": True})
        self.assertEqual(status["error"], "")

    def test_job_records_failure_and_scheduler_keeps_running(self) -> None:
        scheduler = MaintenanceScheduler()

        def fail():
            raise RuntimeError("backup indisponivel")

        job = ScheduledJob("backup", 3600, 0, fail)
        scheduler._status[job.name] = {"name": job.name, "running": False}
        logging.disable(logging.CRITICAL)
        try:
            scheduler._run(job)
        finally:
            logging.disable(logging.NOTSET)
        status = scheduler.status()["jobs"]["backup"]
        self.assertFalse(status["running"])
        self.assertIn("backup indisponivel", status["error"])


if __name__ == "__main__":
    unittest.main()
