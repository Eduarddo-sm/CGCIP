from __future__ import annotations

import time
import unittest
from types import SimpleNamespace

from services.notification_service import NotificationService


class NotificationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.read_calls = 0

        def reads(_user):
            self.read_calls += 1
            return set()

        repo = SimpleNamespace(list_notification_reads=reads)
        self.service = NotificationService(repo, SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
        self.service._overview_notifications = lambda _user: []
        self.service._parecer_notifications = lambda _user, _dismissed: []
        self.service._protocolo_notifications = lambda _user, _dismissed: []

    def test_refresh_reads_dismissed_notifications_only_once(self) -> None:
        payload = self.service.list_notifications("gestor")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(self.read_calls, 1)

    def test_stale_cache_returns_immediately_and_schedules_refresh(self) -> None:
        cached = {"count": 3, "items": [], "version": "old"}
        self.service._cache["gestor"] = (time.monotonic() - 60, cached)
        scheduled = []
        self.service._schedule_refresh = lambda user: scheduled.append(user)
        payload = self.service.list_notifications("gestor")
        self.assertIs(payload, cached)
        self.assertEqual(scheduled, ["gestor"])
        self.assertEqual(self.read_calls, 0)


if __name__ == "__main__":
    unittest.main()
