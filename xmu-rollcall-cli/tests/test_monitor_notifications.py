import unittest
from datetime import datetime
from unittest.mock import patch

from xmu_rollcall.monitor import notify_schedule_window_event


class MonitorNotificationTests(unittest.TestCase):
    @patch("xmu_rollcall.monitor.send_bark_message", return_value=True)
    def test_notify_schedule_window_started(self, mock_send_bark_message):
        started_at = datetime(2026, 4, 13, 8, 0, 0)
        ends_at = datetime(2026, 4, 13, 22, 0, 0)

        result = notify_schedule_window_event(
            "started",
            account_id=7,
            account_name="Alice",
            username="alice123",
            schedule_description="Every day 08:00 - 22:00",
            event_time=started_at,
            window_end=ends_at,
        )

        self.assertTrue(result)
        mock_send_bark_message.assert_called_once_with(
            "Scheduled monitoring started",
            (
                "Account: Alice\n"
                "Schedule: Every day 08:00 - 22:00\n"
                "Started at: 2026-04-13 08:00:00\n"
                "Ends at: 2026-04-13 22:00:00\n"
                "Status: Monitoring is now active."
            ),
            dedupe_key=("monitor_schedule", 7, "started", "2026-04-13 08:00"),
        )

    @patch("xmu_rollcall.monitor.send_bark_message", return_value=True)
    def test_notify_schedule_window_ended_uses_username_when_name_missing(self, mock_send_bark_message):
        ended_at = datetime(2026, 4, 13, 22, 0, 0)
        next_start = datetime(2026, 4, 14, 8, 0, 0)

        result = notify_schedule_window_event(
            "ended",
            account_id=9,
            account_name="",
            username="student01",
            schedule_description="Mon, Tue 08:00 - 22:00",
            event_time=ended_at,
            next_start=next_start,
        )

        self.assertTrue(result)
        mock_send_bark_message.assert_called_once_with(
            "Scheduled monitoring ended",
            (
                "Account: student01\n"
                "Schedule: Mon, Tue 08:00 - 22:00\n"
                "Ended at: 2026-04-13 22:00:00\n"
                "Next start: 2026-04-14 08:00:00\n"
                "Status: Monitoring is paused until the next window."
            ),
            dedupe_key=("monitor_schedule", 9, "ended", "2026-04-13 22:00"),
        )

    def test_notify_schedule_window_event_rejects_unknown_event(self):
        with self.assertRaises(ValueError):
            notify_schedule_window_event(
                "unknown",
                account_id=1,
                account_name="Alice",
                username="alice123",
                schedule_description="Every day 08:00 - 22:00",
            )


if __name__ == "__main__":
    unittest.main()
