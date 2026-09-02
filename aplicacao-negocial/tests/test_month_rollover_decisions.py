from types import SimpleNamespace
import unittest

from fastapi import HTTPException

from backend.services.producao_service import _validated_rollover_decisions


class MonthRolloverDecisionsTest(unittest.TestCase):
    def setUp(self):
        self.candidates = [SimpleNamespace(id=10), SimpleNamespace(id=20)]

    def test_requires_a_classification_for_every_candidate(self):
        with self.assertRaises(HTTPException) as raised:
            _validated_rollover_decisions(self.candidates, [(10, "QUEBRA", True)])
        self.assertEqual(raised.exception.status_code, 422)

    def test_rejects_duplicate_or_invalid_classifications(self):
        with self.assertRaises(HTTPException):
            _validated_rollover_decisions(self.candidates, [(10, "QUEBRA", True), (10, "PROPOSTA_NEGADA", False)])
        with self.assertRaises(HTTPException):
            _validated_rollover_decisions(self.candidates, [(10, "PROPOSTA", True), (20, "QUEBRA", False)])

    def test_accepts_break_and_denied_proposal(self):
        decisions = _validated_rollover_decisions(
            self.candidates,
            [(10, "QUEBRA", True), (20, "PROPOSTA_NEGADA", False)],
        )
        self.assertEqual(decisions, {10: ("QUEBRA", True), 20: ("PROPOSTA_NEGADA", False)})


if __name__ == "__main__":
    unittest.main()
