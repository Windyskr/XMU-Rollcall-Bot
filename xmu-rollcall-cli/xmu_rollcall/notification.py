from urllib.parse import parse_qsl, quote, urlparse, urlunparse

import requests

from .config import load_config

_SENT_EVENTS = set()
_DEFAULT_BARK_GROUP = "XMU Rollcall Bot"


def get_bark_url():
    return load_config().get("bark_url", "").strip()


def _build_bark_request(title, body, bark_url):
    parsed = urlparse(bark_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "Invalid Bark URL. Please use a full URL such as https://api.day.app/<device_key>."
        )

    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.setdefault("group", _DEFAULT_BARK_GROUP)
    normalized_path = parsed.path.rstrip("/")

    if normalized_path.endswith("/push") or (
        not normalized_path and ("device_key" in query_params or "key" in query_params)
    ):
        request_path = normalized_path or "/push"
        request_url = urlunparse(parsed._replace(path=request_path, query="", fragment=""))
        request_params = dict(query_params)
        request_params["title"] = title
        request_params["body"] = body
        return request_url, request_params

    if not normalized_path:
        raise ValueError(
            "Bark URL must include a device key, or use the /push endpoint with device_key."
        )

    request_path = f"{normalized_path}/{quote(title, safe='')}/{quote(body, safe='')}"
    request_url = urlunparse(parsed._replace(path=request_path, query="", fragment=""))
    return request_url, query_params


def _response_text_snippet(response, limit=160):
    text = (response.text or "").strip().replace("\r", " ").replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _get_bark_error(response):
    if not response.ok:
        snippet = _response_text_snippet(response)
        if snippet:
            return f"HTTP {response.status_code}: {snippet}"
        return f"HTTP {response.status_code}"

    try:
        payload = response.json()
    except ValueError:
        return None

    if isinstance(payload, dict):
        bark_code = payload.get("code")
        if bark_code not in (None, 0, 200):
            bark_message = payload.get("message") or payload.get("error") or "unknown error"
            return f"{bark_message} (code={bark_code})"

    return None


def send_bark_message(title, body, bark_url=None, dedupe_key=None):
    bark_url = (bark_url or get_bark_url()).strip()
    if not bark_url:
        return False

    if dedupe_key is not None and dedupe_key in _SENT_EVENTS:
        return False

    try:
        request_url, request_params = _build_bark_request(title, body, bark_url)
        response = requests.get(request_url, params=request_params, timeout=5)
        bark_error = _get_bark_error(response)
        if bark_error:
            print(f"[Bark] Notification failed: {bark_error}")
            return False
        if dedupe_key is not None:
            _SENT_EVENTS.add(dedupe_key)
        return True
    except Exception as exc:
        print(f"[Bark] Notification failed: {exc}")
        return False
