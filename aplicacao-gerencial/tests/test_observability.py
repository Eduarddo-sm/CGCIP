from __future__ import annotations

import json
import logging
import unittest

from services.observability import JsonFormatter, new_request_id


class ObservabilityTestCase(unittest.TestCase):
    def test_request_id_preserves_valid_client_value(self) -> None:
        self.assertEqual(new_request_id("trace-123"), "trace-123")

    def test_request_id_generates_value_when_missing(self) -> None:
        self.assertEqual(len(new_request_id()), 32)

    def test_json_log_contains_http_fields(self) -> None:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)
        record.request_id = "request-7"
        record.status = 200
        record.duration_ms = 12.5
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["request_id"], "request-7")
        self.assertEqual(payload["status"], 200)
        self.assertEqual(payload["duration_ms"], 12.5)


if __name__ == "__main__":
    unittest.main()
