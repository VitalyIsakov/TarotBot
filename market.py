"""Рыночные данные: индекс Мосбиржи и RGBI — MOEX ISS, USD/RUB — официальный курс ЦБ."""
import datetime as dt
import time
import requests

UA = {"User-Agent": "tarot-markets-bot/1.0"}
ISS = "https://iss.moex.com/iss"


def _get(url, attempts=6, **kw):
    """GET с повторами: ISS Мосбиржи периодически рвёт соединения."""
    for i in range(attempts):
        try:
            r = requests.get(url, headers=UA, timeout=20, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(3 * (i + 1))


def _moex_index(secid):
    since = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    r = _get(f"{ISS}/history/engines/stock/markets/index/securities/{secid}.json",
             params={"from": since, "iss.meta": "off", "history.columns": "TRADEDATE,CLOSE"})
    rows = [x for x in r.json()["history"]["data"] if x[1] is not None]
    if len(rows) < 2:
        raise RuntimeError(f"{secid}: мало данных")
    last_date, last = rows[-1]
    prev = rows[-2][1]
    week_ago = rows[-6][1] if len(rows) >= 6 else rows[0][1]
    return {"date": last_date, "close": last,
            "chg_1d": (last / prev - 1) * 100, "chg_5d": (last / week_ago - 1) * 100}


def _cbr_usd():
    r = _get("https://www.cbr-xml-daily.ru/daily_json.js")
    d = r.json()
    usd = d["Valute"]["USD"]
    val, prev = usd["Value"] / usd["Nominal"], usd["Previous"] / usd["Nominal"]
    week = None
    base = dt.date.fromisoformat(d["Date"][:10])
    for back in range(7, 11):  # курс неделю назад из архива (ищем ближайший рабочий день)
        day = base - dt.timedelta(days=back)
        try:
            a = requests.get(f"https://www.cbr-xml-daily.ru/archive/{day:%Y/%m/%d}/daily_json.js",
                             headers=UA, timeout=20)
            if a.ok:
                u = a.json()["Valute"]["USD"]
                week = (val / (u["Value"] / u["Nominal"]) - 1) * 100
                break
        except Exception:
            pass
    return {"date": d["Date"][:10], "close": round(val, 4),
            "chg_1d": (val / prev - 1) * 100, "chg_5d": week}


ASSETS = {
    "IMOEX": {"title": "Индекс Мосбиржи", "emoji": "📈", "fetch": lambda: _moex_index("IMOEX")},
    "RGBI": {"title": "RGBI (гособлигации)", "emoji": "🏦", "fetch": lambda: _moex_index("RGBI")},
    "USDRUB": {"title": "USD/RUB (курс ЦБ)", "emoji": "💵", "fetch": _cbr_usd},
}


def fetch_all():
    out = {}
    for key, a in ASSETS.items():
        try:
            out[key] = a["fetch"]()
        except Exception as e:  # пост выйдет и без цифр по одному активу
            print(f"[market] {key}: {e}")
            out[key] = None
    return out


# ---------- подписи дат (общие для текста и картинки) ----------
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WD_ACC = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]  # «на …», «в …»
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
SHORT = {"IMOEX": "индекс", "RGBI": "RGBI", "USDRUB": "доллар"}


def _d(x):
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def day_short(x):
    """пт 02.10"""
    d = _d(x)
    return f"{WD[d.weekday()]} {d:%d.%m}"


def day_long(x):
    """пятницу, 2 октября"""
    d = _d(x)
    return f"{WD_ACC[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def asof(key, m):
    """За какой день цифра: закрытие биржи или дата, с которой действует курс ЦБ."""
    if not m:
        return "нет данных"
    return f"курс ЦБ с {day_short(m['date'])}" if key == "USDRUB" else f"закрытие {day_short(m['date'])}"


def dateline(forecast_day, mkt):
    """Строка под заголовком поста: на какой день прогноз и за какие дни котировки."""
    groups = {}
    for k, m in mkt.items():
        if m:
            groups.setdefault(asof(k, m), []).append(SHORT[k])
    data = "; ".join(f"{' и '.join(names)} — {lab}" for lab, names in groups.items()) or "нет данных"
    return f"🗓 <b>Прогноз на {day_long(forecast_day)}</b>\n<i>Котировки: {data}</i>"
