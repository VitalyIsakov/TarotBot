"""Публикация в Telegram через Bot API.

Два формата поста (переменная POST_LAYOUT):
- preview — обычное текстовое сообщение во всю ширину экрана, картинка расклада большим превью над текстом.
  Картинка кладётся в папку media/ репозитория и берётся по публичной ссылке raw.githubusercontent.com,
  поэтому репозиторий на GitHub должен быть публичным. Режим по умолчанию при запуске в GitHub Actions.
- caption — картинка с подписью. На телефоне подпись не шире картинки (~75% экрана). Запасной режим:
  включается сам, если картинку не удалось выложить по ссылке.
"""
import json
import os
import secrets
import shutil
import subprocess
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


def _api(method):
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"


def _check(r):
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram: {j}")
    return j


# ---------- размещение картинки по публичной ссылке ----------

def _git(*args):
    subprocess.run(["git", "-c", "user.name=tarot-bot", "-c", "user.email=tarot-bot@users.noreply.github.com",
                    *args], cwd=HERE, check=True, capture_output=True, text=True)


def host_image(image_path):
    """Кладёт картинку в media/, пушит в репозиторий и возвращает публичную ссылку на неё."""
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")
    name = f"{time.strftime('%Y-%m-%d')}_{secrets.token_hex(4)}.jpg"  # уникальное имя: Telegram кэширует превью
    os.makedirs(os.path.join(HERE, "media"), exist_ok=True)
    shutil.copy(image_path, os.path.join(HERE, "media", name))
    _git("add", f"media/{name}")
    _git("commit", "-m", f"media: {name}")
    try:
        _git("push", "origin", f"HEAD:{branch}")
    except subprocess.CalledProcessError:
        _git("pull", "--rebase", "origin", branch)
        _git("push", "origin", f"HEAD:{branch}")

    url = f"https://raw.githubusercontent.com/{repo}/{branch}/media/{name}"
    for _ in range(20):  # ждём, пока ссылка начнёт отдавать картинку
        try:
            r = requests.get(url, timeout=15)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                return url
        except requests.RequestException:
            pass
        time.sleep(3)
    raise RuntimeError(f"картинка недоступна по ссылке {url} — репозиторий на GitHub публичный?")


# ---------- отправка ----------

def _send_preview(chat_id, text, url):
    # невидимая ссылка в начале текста + явные параметры превью: картинка крупно и над текстом
    html = f'<a href="{url}">​</a>' + text
    return _check(requests.post(_api("sendMessage"), timeout=60, data={
        "chat_id": chat_id, "text": html, "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": url, "prefer_large_media": True, "show_above_text": True}),
    }))


def _send_caption(chat_id, image_path, text):
    if len(text) <= CAPTION_LIMIT:  # один пост: картинка + подпись
        with open(image_path, "rb") as f:
            return _check(requests.post(_api("sendPhoto"), timeout=60, files={"photo": f},
                                        data={"chat_id": chat_id, "caption": text, "parse_mode": "HTML"}))
    with open(image_path, "rb") as f:
        _check(requests.post(_api("sendPhoto"), timeout=60, files={"photo": f}, data={"chat_id": chat_id}))
    return _check(requests.post(_api("sendMessage"), timeout=60,
                                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}))


def publish(image_path, text, chat_id=None):
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    layout = os.getenv("POST_LAYOUT") or ("preview" if os.getenv("GITHUB_REPOSITORY") else "caption")
    if layout == "preview" and len(text) < TEXT_LIMIT - 300:
        try:
            url = host_image(image_path)
        except Exception as e:  # не удалось выложить картинку — публикуем по-старому, день не пропадает
            print(f"[telegram] превью недоступно, публикуем картинкой с подписью: {e}")
        else:
            return _send_preview(chat_id, text, url)  # ошибки отправки не глушим, чтобы не задвоить пост
    return _send_caption(chat_id, image_path, text)
