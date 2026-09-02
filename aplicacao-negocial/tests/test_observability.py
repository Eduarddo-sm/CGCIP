import json
import logging
import unittest

from backend.observability import JsonFormatter, request_id, request_id_context


class ObservabilityTest(unittest.TestCase):
    def test_request_id_preserves_valid_client_value(self):
        self.assertEqual(request_id("trace-123"), "trace-123")

    def test_request_id_generates_value_when_missing(self):
        self.assertEqual(len(request_id()), 32)

    def test_json_formatter_includes_request_context(self):
        token = request_id_context.set("request-42")
        try:
            record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)
            payload = json.loads(JsonFormatter().format(record))
        finally:
            request_id_context.reset(token)
        self.assertEqual(payload["request_id"], "request-42")
        self.assertEqual(payload["message"], "completed")


if __name__ == "__main__":
    unittest.main()
