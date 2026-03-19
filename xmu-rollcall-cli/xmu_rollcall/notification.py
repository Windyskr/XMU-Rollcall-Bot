from urllib.parse import quote

import requests

from .config import load_config

_SENT_EVENTS = set()


def get_bark_url():
    return load_config().get("bark_url", "").strip()


def send_bark_message(title, body, bark_url=None, dedupe_key=None):
    bark_url = (bark_url or get_bark_url()).strip()
    if not bark_url:
        return False

    if dedupe_key is not None and dedupe_key in _SENT_EVENTS:
        return False

    request_url = f"{bark_url.rstrip('/')}/{quote(title, safe='')}/{quote(body, safe='')}"

    try:
        response = requests.get(
            request_url,
            params={"group": "XMU Rollcall Bot"},
            timeout=5,
        )
        if response.ok and dedupe_key is not None:
            _SENT_EVENTS.add(dedupe_key)
        return response.ok
    except Exception:
        return False
