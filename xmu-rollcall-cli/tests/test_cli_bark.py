import unittest
from unittest.mock import patch

from xmu_rollcall.cli import save_bark_url_and_send_test


class SaveBarkUrlAndSendTestTests(unittest.TestCase):
    @patch("xmu_rollcall.cli.save_config")
    @patch("xmu_rollcall.cli.send_bark_message", return_value=True)
    def test_save_and_send_test_notification_when_url_is_present(self, mock_send_bark_message, mock_save_config):
        config = {}

        result = save_bark_url_and_send_test(config, "  https://api.day.app/device_key  ")

        self.assertTrue(result)
        self.assertEqual(config["bark_url"], "https://api.day.app/device_key")
        mock_save_config.assert_called_once_with(config)
        mock_send_bark_message.assert_called_once_with(
            "XMU Rollcall Bot Test",
            "If you received this message, Bark notifications are working.",
            bark_url="https://api.day.app/device_key",
        )

    @patch("xmu_rollcall.cli.save_config")
    @patch("xmu_rollcall.cli.send_bark_message")
    def test_save_without_sending_when_url_is_empty(self, mock_send_bark_message, mock_save_config):
        config = {"bark_url": "https://api.day.app/device_key"}

        result = save_bark_url_and_send_test(config, "   ")

        self.assertIsNone(result)
        self.assertEqual(config["bark_url"], "")
        mock_save_config.assert_called_once_with(config)
        mock_send_bark_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
