import unittest
from unittest.mock import Mock, patch

from xmu_rollcall import notification


class BarkNotificationTests(unittest.TestCase):
    def setUp(self):
        notification._SENT_EVENTS.clear()

    @staticmethod
    def _mock_response(ok=True, status_code=200, json_payload=None, text=""):
        response = Mock()
        response.ok = ok
        response.status_code = status_code
        response.text = text
        if json_payload is None:
            response.json.side_effect = ValueError("No JSON body")
        else:
            response.json.return_value = json_payload
        return response

    @patch("xmu_rollcall.notification.requests.get")
    def test_send_bark_message_supports_device_key_path(self, mock_get):
        mock_get.return_value = self._mock_response(json_payload={"code": 200, "message": "success"})

        result = notification.send_bark_message(
            "Detected new rollcall",
            "Course/1",
            bark_url="https://api.day.app/device_key",
        )

        self.assertTrue(result)
        mock_get.assert_called_once_with(
            "https://api.day.app/device_key/Detected%20new%20rollcall/Course%2F1",
            params={"group": "XMU Rollcall Bot"},
            timeout=5,
        )

    @patch("xmu_rollcall.notification.requests.get")
    def test_send_bark_message_supports_push_endpoint(self, mock_get):
        mock_get.return_value = self._mock_response(json_payload={"code": 200, "message": "success"})

        result = notification.send_bark_message(
            "Auto rollcall succeeded",
            "Course: Test",
            bark_url="https://api.day.app/push?device_key=device123&sound=bell",
        )

        self.assertTrue(result)
        mock_get.assert_called_once_with(
            "https://api.day.app/push",
            params={
                "device_key": "device123",
                "sound": "bell",
                "group": "XMU Rollcall Bot",
                "title": "Auto rollcall succeeded",
                "body": "Course: Test",
            },
            timeout=5,
        )

    @patch("builtins.print")
    @patch("xmu_rollcall.notification.requests.get")
    def test_send_bark_message_detects_api_error_payload(self, mock_get, mock_print):
        mock_get.return_value = self._mock_response(
            json_payload={"code": 400, "message": "invalid device key"}
        )

        result = notification.send_bark_message(
            "Detected new rollcall",
            "Course: Test",
            bark_url="https://api.day.app/device_key",
        )

        self.assertFalse(result)
        mock_print.assert_called_once_with(
            "[Bark] Notification failed: invalid device key (code=400)"
        )


if __name__ == "__main__":
    unittest.main()
