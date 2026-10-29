import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from source import parse_record, aggregate


class SourceBoundaries(unittest.TestCase):
    def row(self, **values):
        return dict(
            unique_key="fixture",
            created_date="2026-04-01T12:00:00.000",
            agency="DOT",
            status="Closed",
            **values
        )

    def test_same_calendar_day(self):
        self.assertEqual(
            parse_record(
                self.row(closed_date="2026-04-01T15:00:00"), date(2026, 10, 29)
            )[1],
            ("DOT", "4", "1", "0", "closed", "eligible"),
        )

    def test_backward_same_day_is_quarantined(self):
        self.assertEqual(
            parse_record(
                self.row(closed_date="2026-04-01T11:00:00"), date(2026, 10, 29)
            )[1][-1],
            "closure_before_creation",
        )

    def test_absent_closure_is_preserved(self):
        self.assertEqual(
            parse_record(self.row(), date(2026, 10, 29))[1][3:5], ("missing", "closed")
        )

    def test_long_delay_cell(self):
        self.assertEqual(
            parse_record(
                self.row(closed_date="2026-07-01T12:00:00"), date(2026, 10, 29)
            )[1][3],
            "gt45",
        )

    def test_future_closure_is_quarantined(self):
        self.assertEqual(
            parse_record(
                self.row(closed_date="2026-10-30T12:00:00"), date(2026, 10, 29)
            )[1][-1],
            "closure_after_capture",
        )

    def test_extra_field_is_rejected(self):
        with self.assertRaises(AssertionError):
            parse_record(self.row(address="excluded"), date(2026, 10, 29))

    def test_duplicate_id_is_rejected(self):
        with self.assertRaises(AssertionError):
            aggregate([self.row(), self.row()], date(2026, 10, 29))


if __name__ == "__main__":
    unittest.main()
