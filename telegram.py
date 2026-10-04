"""Публикация в Telegram через Bot API."""
import os
import requests

CAPTION_LIMIT = 1024


def _api(method):
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"


def _check(r):
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram: {j}")
    return j


def publish(image_path, text, chat_id=None):
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    if len(text) <= CAPTION_LIMIT:  # один пост: картинка + подпись
        with open(image_path, "rb") as f:
            return _check(requests.post(_api("sendPhoto"), timeout=60, files={"photo": f},
                                        data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"}))
    with open(image_path, "rb") as f:
        _check(requests.post(_api("sendPhoto"), timeout=60, files={"photo": f}, data={"chat_id": chat_id}))
    return _check(requests.post(_api("sendMessage"), timeout=60,
                                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}))
