from __future__ import annotations

import unicodedata
from typing import Any


class DiffService:
    def compare(self, before: dict[str, Any] | None, after: dict[str, Any], key_column: str | None = None) -> dict[str, Any]:
        if before is None:
            return {
                "summary": {
                    "cells_changed": 0,
                    "rows_added": len(after["rows"]),
                    "rows_removed": 0,
                    "columns_added": len(after["headers"]),
                    "columns_removed": 0,
                    "columns_changed": 0,
                    "structure_changed": True,
                },
                "changes": [
                    {
                        "type": "initial_snapshot",
                        "message": "Snapshot inicial criado",
                        "rows_added": len(after["rows"]),
                        "columns": after["headers"],
                    }
                ],
            }

        before_headers = before.get("headers", [])
        after_headers = after.get("headers", [])
        before_header_map = self._header_map(before_headers)
        after_header_map = self._header_map(after_headers)
        added_keys = set(after_header_map) - set(before_header_map)
        removed_keys = set(before_header_map) - set(after_header_map)
        resolved_key = self._resolve_key_column(after_headers, before_headers, key_column)
        before_rows = self._index_rows(before.get("rows", []), resolved_key)
        after_rows = self._index_rows(after.get("rows", []), resolved_key)
        columns_added = [
            after_header_map[self._header_key(column)]
            for column in after_headers
            if self._header_key(column) in added_keys
            and self._column_non_empty_count(after_rows.values(), after_header_map[self._header_key(column)]) > 0
        ]
        columns_removed = [
            before_header_map[self._header_key(column)]
            for column in before_headers
            if self._header_key(column) in removed_keys
            and self._column_non_empty_count(before_rows.values(), before_header_map[self._header_key(column)]) > 0
        ]
        changes = []

        for row_id in sorted(after_rows.keys() - before_rows.keys(), key=self._row_sort):
            changes.append({"type": "row_added", "row_id": row_id, "key_column": resolved_key, "after": after_rows[row_id]})
        for row_id in sorted(before_rows.keys() - after_rows.keys(), key=self._row_sort):
            changes.append({"type": "row_removed", "row_id": row_id, "key_column": resolved_key, "before": before_rows[row_id]})

        shared_columns = [
            (before_header_map[self._header_key(column)], after_header_map[self._header_key(column)])
            for column in after_headers
            if self._header_key(column) in before_header_map
        ]
        cells_changed = 0
        for row_id in sorted(before_rows.keys() & after_rows.keys(), key=self._row_sort):
            before_row = before_rows[row_id]
            after_row = after_rows[row_id]
            for before_column, after_column in shared_columns:
                before_value = before_row.get(before_column)
                after_value = after_row.get(after_column)
                if self._normalized_cell_value(before_value) != self._normalized_cell_value(after_value):
                    cells_changed += 1
                    changes.append(
                        {
                            "type": "cell_changed",
                            "row_id": row_id,
                            "key_column": resolved_key,
                            "excel_row": after_row.get("_excel_row"),
                            "column": after_column,
                            "before": before_value,
                            "after": after_value,
                            "row_before": before_row,
                            "row_after": after_row,
                        }
                    )

        for column in columns_added:
            changes.append({
                "type": "column_added",
                "column": column,
                "non_empty_values": self._column_non_empty_count(after_rows.values(), column),
            })
        for column in columns_removed:
            changes.append({
                "type": "column_removed",
                "column": column,
                "non_empty_values": self._column_non_empty_count(before_rows.values(), column),
            })

        return {
            "summary": {
                "cells_changed": cells_changed,
                "rows_added": len(after_rows.keys() - before_rows.keys()),
                "rows_removed": len(before_rows.keys() - after_rows.keys()),
                "columns_added": len(columns_added),
                "columns_removed": len(columns_removed),
                "columns_changed": len(columns_added) + len(columns_removed),
                "structure_changed": bool(columns_added or columns_removed or before.get("table_range") != after.get("table_range")),
                "key_column": resolved_key,
            },
            "changes": changes,
        }

    def _row_sort(self, row_id: str) -> int:
        try:
            return int(row_id)
        except ValueError:
            return abs(hash(row_id))

    def _resolve_key_column(self, after_headers: list[str], before_headers: list[str], key_column: str | None) -> str | None:
        if not key_column:
            return None
        headers = [*after_headers, *before_headers]
        for header in headers:
            if self._header_key(header) == self._header_key(key_column):
                return header
        return None

    def _header_key(self, value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        return " ".join("".join(character if character.isalnum() else " " for character in text).upper().split())

    def _header_map(self, headers: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for header in headers:
            key = self._header_key(header)
            if key and key not in result:
                result[key] = header
        return result

    def _normalized_cell_value(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"", "none", "null", "nan", "vazio"}:
            return ""
        return " ".join(text.split())

    def _index_rows(self, rows: list[dict[str, Any]], key_column: str | None) -> dict[str, dict[str, Any]]:
        indexed = {}
        seen = set()
        for position, row in enumerate(rows):
            if not self._row_has_content(row):
                continue
            row_key = self._row_key(row, key_column)
            if row_key in seen:
                row_key = f"{row_key}|row:{row.get('_row_id', position)}"
            while row_key in seen:
                row_key = f"{row_key}:{position}"
            seen.add(row_key)
            indexed[row_key] = row
        return indexed

    def _row_key(self, row: dict[str, Any], key_column: str | None) -> str:
        if key_column:
            value = self._row_value(row, key_column)
            normalized = self._normalized_cell_value(value)
            if normalized:
                return f"key:{normalized}"
        return f"row:{row.get('_row_id')}"

    def _row_value(self, row: dict[str, Any], column: str) -> Any:
        if column in row:
            return row.get(column)
        column_key = self._header_key(column)
        for key, value in row.items():
            if not str(key).startswith("_") and self._header_key(key) == column_key:
                return value
        return None

    def _row_has_content(self, row: dict[str, Any]) -> bool:
        return any(
            self._normalized_cell_value(value)
            for key, value in row.items()
            if not str(key).startswith("_")
        )

    def _column_non_empty_count(self, rows: Any, column: str) -> int:
        return sum(1 for row in rows if self._normalized_cell_value(self._row_value(row, column)))
