from __future__ import annotations

import unittest
from datetime import date

from backend.services.producao_calendar import (
    can_move_to_next_month,
    current_month_start,
    month_range,
    previous_month_start,
    rollover_deadline_reached,
    second_business_day,
)


class ProducaoCalendarTest(unittest.TestCase):
    def test_month_range_handles_year_boundary(self):
        self.assertEqual(month_range(date(2026, 12, 15)), (date(2026, 12, 1), date(2027, 1, 1)))

    def test_current_month_start_uses_reference(self):
        self.assertEqual(current_month_start(date(2026, 7, 14)), date(2026, 7, 1))

    def test_next_month_is_available_only_in_last_five_days(self):
        self.assertFalse(can_move_to_next_month(date(2026, 7, 25)))
        self.assertTrue(can_move_to_next_month(date(2026, 7, 26)))
        self.assertTrue(can_move_to_next_month(date(2026, 7, 31)))

    def test_previous_month_handles_year_boundary(self):
        self.assertEqual(previous_month_start(date(2026, 1, 10)), date(2025, 12, 1))

    def test_second_business_day_skips_weekend(self):
        self.assertEqual(second_business_day(date(2026, 8, 1)), date(2026, 8, 4))

    def test_second_business_day_skips_national_holiday(self):
        self.assertEqual(second_business_day(date(2026, 5, 1)), date(2026, 5, 5))

    def test_rollover_deadline_is_reached_on_second_business_day(self):
        self.assertFalse(rollover_deadline_reached(date(2026, 8, 3)))
        self.assertTrue(rollover_deadline_reached(date(2026, 8, 4)))


if __name__ == "__main__":
    unittest.main()
