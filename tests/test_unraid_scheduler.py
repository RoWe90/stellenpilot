"""The optional daily sidecar should not run twice after restart."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from stellenpilot.unraid_scheduler import due, parse_time


class UnraidSchedulerTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(parse_time("08:45"), (8, 45))
        for invalid in ["24:00", "8:45", "00:60", "08:45; rm -rf /"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_time(invalid)

    def test_daily_once_and_after_restart(self):
        zone = ZoneInfo("Europe/Berlin")
        day = datetime(2026, 10, 23, 9, 1, tzinfo=zone)
        self.assertTrue(due(day, (8, 45), ""))
        self.assertFalse(due(day, (8, 45), "2026-10-23"))
        self.assertFalse(due(day.replace(hour=8, minute=44), (8, 45), ""))
        self.assertTrue(due(day.replace(day=24), (8, 45), "2026-10-23"))


if __name__ == "__main__":
    unittest.main()
