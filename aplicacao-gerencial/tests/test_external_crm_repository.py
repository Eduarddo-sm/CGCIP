from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from database.external_crm_repository import ExternalCrmRepository, LAST_ACTION_COLUMNS


class ExternalCrmRepositoryTests(unittest.TestCase):
    def make_repository(self) -> ExternalCrmRepository:
        repository = ExternalCrmRepository.__new__(ExternalCrmRepository)
        repository.table = '"public"."acionamentos"'
        repository.engine = object()
        return repository

    @patch("database.external_crm_repository.pd.read_sql_query")
    def test_latest_actions_bundle_uses_one_array_query_and_splits_scopes(self, read_query) -> None:
        manual = {column: None for column in LAST_ACTION_COLUMNS}
        manual.update({"contrato": "1", "contrato_key_db": "1", "action_scope": "manual"})
        dialer = {column: None for column in LAST_ACTION_COLUMNS}
        dialer.update({"contrato": "2", "contrato_key_db": "2", "action_scope": "discador"})
        read_query.return_value = pd.DataFrame([manual, dialer])

        actions, discador = self.make_repository().latest_actions_bundle(["0001", "2", "2"])

        self.assertEqual(read_query.call_count, 1)
        query, _engine = read_query.call_args.args
        params = read_query.call_args.kwargs["params"]
        self.assertIn("UNNEST", str(query))
        self.assertIn("ANY", str(query))
        self.assertNotIn("POSTCOMPILE", str(query))
        self.assertEqual(params["contracts"], ["1", "2"])
        self.assertEqual(actions["contrato"].tolist(), ["1"])
        self.assertEqual(discador["contrato"].tolist(), ["2"])
        self.assertEqual(actions.columns.tolist(), LAST_ACTION_COLUMNS)

    @patch("database.external_crm_repository.pd.read_sql_query")
    def test_latest_actions_compatibility_method_returns_requested_scope(self, read_query) -> None:
        row = {column: None for column in LAST_ACTION_COLUMNS}
        row.update({"contrato": "2", "contrato_key_db": "2", "action_scope": "discador"})
        read_query.return_value = pd.DataFrame([row])

        result = self.make_repository().latest_actions(["2"], discador=True)

        self.assertEqual(result["contrato"].tolist(), ["2"])
        self.assertEqual(read_query.call_count, 1)


if __name__ == "__main__":
    unittest.main()
