"""Свежие рыночные новости для поста: заголовки из RSS-лент, отобранные по значимости для рынка.

Модель получает только заголовки с датой и источником и упоминает 1–2 самых важных события.
Если ленты недоступны, пост выходит без новостей — расклад от этого не зависит.
"""
import datetime as dt
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

import market

TZ = ZoneInfo("Europe/Moscow")
UA = {"User-Agent": "Mozilla/5.0 (tarot-markets-bot)"}

# (источник, адрес ленты, рубрики — None значит «все»)
FEEDS = [
    ("Финам", "https://www.finam.ru/analysis/conews/rsspoint/", None),
    ("Коммерсант", "https://www.kommersant.ru/RSS/section-economics.xml", None),
    ("Интерфакс", "https://www.interfax.ru/rss.asp", {"Экономика"}),
    ("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", {"Экономика", "Финансы", "Бизнес"}),
    ("ТАСС", "https://tass.ru/rss/v2.xml", {"Экономика и бизнес"}),
]

# Чем больше совпадений, тем выше заголовок в списке
KEYWORDS = {
    3: ["ключев", "ставк", "банк росси", " цб", "инфляц", "мосбирж", "индекс", "imoex", "rgbi", "офз", "минфин",
        "рубл", "доллар", "юан", "курс", "нефт", "brent", "urals", "санкц", "пошлин"],
    2: ["акци", "облигац", "дивиденд", "отчёт", "отчет", "мсфо", "рсбу", "ipo", "spo", "размещени", "аукцион",
        "бюджет", "налог", "газ", "опек", "экспорт", "импорт", "торг", "рынок", "биржа", "инвест", "капитализац"],
    1: ["сбер", "газпром", "лукойл", "роснефть", "новатэк", "втб", "яндекс", "т-банк", "норникел", "алроса",
        "магнит", "полюс", "мтс", "ozon", "x5", "трамп", "сша", "китай", "евросоюз"],
}
# Заголовки про войну, жертвы и катастрофы в шуточный канал не берём
EXCLUDE = re.compile(r"погиб|убит|жертв|ранен|теракт|атак|обстрел|всу|сво\b|войск|бпла|беспилот|ракетн|взрыв|"
                     r"катастроф|пострадав|задержан|арест|суд приговор", re.I)


def _since(day):
    """Начало окна новостей: 09:00 МСК предыдущего торгового дня (в понедельник — с пятницы)."""
    prev = day - dt.timedelta(days=1)
    while not market.is_trading_day(prev):
        prev -= dt.timedelta(days=1)
    return dt.datetime.combine(prev, dt.time(9, 0), TZ)


def _score(title):
    low = " " + title.lower()
    return sum(w for w, words in KEYWORDS.items() for k in words if k in low)


def _load(source, url, cats, since):
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[news] {source}: {e}")
        return []
    out = []
    for it in root.iter("item"):
        title = " ".join((it.findtext("title") or "").split())
        title = re.sub(r"\s+в (субботу|воскресенье|выходные)\b", "", title)  # про выходные в канале не говорим
        cat = (it.findtext("category") or "").strip()
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(TZ)
        except Exception:
            continue
        if not title or when < since or (cats and cat not in cats) or EXCLUDE.search(title):
            continue
        out.append({"source": source, "title": title[:180], "when": when, "score": _score(title)})
    return out


def fetch(day, hours=None, limit=15):
    """Самые значимые для рынка заголовки с момента прошлой сессии, свежие сверху."""
    now = dt.datetime.now(TZ)
    since = now - dt.timedelta(hours=hours) if hours else _since(day)
    items, seen = [], set()
    for source, url, cats in FEEDS:
        for x in _load(source, url, cats, since):
            key = re.sub(r"\W+", "", x["title"].lower())[:60]
            if key not in seen:
                seen.add(key)
                items.append(x)
    items = [x for x in items if x["score"] > 0]
    items.sort(key=lambda x: (x["score"], x["when"]), reverse=True)
    top = sorted(items[:limit], key=lambda x: x["when"], reverse=True)
    print(f"[news] заголовков в работе: {len(top)} из {len(items)} подходящих")
    return [f"{x['when']:%d.%m %H:%M} — {x['title']} ({x['source']})" for x in top]


if __name__ == "__main__":
    for line in fetch(dt.datetime.now(TZ).date()):
        print(line)
