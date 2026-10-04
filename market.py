"""Рыночные данные с Мосбиржи (ISS): индекс IMOEX, индекс гособлигаций RGBI и курс доллара.

Доллар — по вечному фьючерсу USDRUBF: с июня 2024 г. спот USD/RUB на бирже не торгуется,
фиксинг по доллару не считается, а «индикативный курс» совпадает с курсом ЦБ.
Цена доллара за день — закрытие основной сессии (последняя сделка до 19:00 МСК), а не вечерней:
дневная история биржи по фьючерсам даёт цену конца вечерней сессии (~23:50).
"""
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


def _moex_history(engine, market, secid):
    """Дневные закрытия инструмента: последнее, изменение за день и за 5 торговых дней."""
    since = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    r = _get(f"{ISS}/history/engines/{engine}/markets/{market}/securities/{secid}.json",
             params={"from": since, "iss.meta": "off", "history.columns": "TRADEDATE,CLOSE"})
    rows = [x for x in r.json()["history"]["data"] if x[1] is not None]
    if len(rows) < 2:
        raise RuntimeError(f"{secid}: мало данных")
    last_date, last = rows[-1]
    prev = rows[-2][1]
    week_ago = rows[-6][1] if len(rows) >= 6 else rows[0][1]
    return {"date": last_date, "close": last,
            "chg_1d": (last / prev - 1) * 100, "chg_5d": (last / week_ago - 1) * 100}


def _moex_futures_main_close(secid):
    """Закрытия основной сессии (последняя сделка до 19:00 МСК) по будним дням из часовых свечей."""
    since = (dt.date.today() - dt.timedelta(days=16)).isoformat()
    r = _get(f"{ISS}/engines/futures/markets/forts/securities/{secid}/candles.json",
             params={"from": since, "interval": 60, "iss.meta": "off", "candles.columns": "begin,close"})
    by_day = {}
    for begin, close in r.json()["candles"]["data"]:
        day, hour = begin[:10], int(begin[11:13])
        if hour < 19 and dt.date.fromisoformat(day).weekday() < 5:
            by_day.setdefault(day, {})[hour] = close
    # день засчитываем, только если основная сессия уже закончилась (есть свеча 18:00)
    rows = [(d, h[max(h)]) for d, h in sorted(by_day.items()) if 18 in h]
    if len(rows) < 2:
        raise RuntimeError(f"{secid}: мало данных")
    last_date, last = rows[-1]
    prev = rows[-2][1]
    week_ago = rows[-6][1] if len(rows) >= 6 else rows[0][1]
    return {"date": last_date, "close": last,
            "chg_1d": (last / prev - 1) * 100, "chg_5d": (last / week_ago - 1) * 100}


ASSETS = {
    "IMOEX": {"title": "Индекс Мосбиржи", "emoji": "📈",
              "fetch": lambda: _moex_history("stock", "index", "IMOEX")},
    "RGBI": {"title": "RGBI (гособлигации)", "emoji": "🏦",
             "fetch": lambda: _moex_history("stock", "index", "RGBI")},
    "USDRUB": {"title": "USDRUBF (вечный фьючерс на доллар)", "emoji": "💵",
               "fetch": lambda: _moex_futures_main_close("USDRUBF")},
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
SHORT = {"IMOEX": "индекс", "RGBI": "RGBI", "USDRUB": "USDRUBF"}


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
    """За какой торговый день цифра."""
    return f"закрытие {day_short(m['date'])}" if m else "нет данных"


def dateline(forecast_day, mkt):
    """Строка под заголовком поста: на какой день прогноз и за какой день котировки."""
    groups = {}
    for k, m in mkt.items():
        if m:
            groups.setdefault(asof(k, m), []).append(SHORT[k])
    if len(groups) == 1:  # обычный случай: все котировки за один день
        data = next(iter(groups))
    else:
        data = "; ".join(f"{', '.join(n)} — {lab}" for lab, n in groups.items()) or "нет данных"
    return f"🗓 <b>Прогноз на {day_long(forecast_day)}</b>\n<i>Котировки: {data}</i>"


# Нерабочие праздничные дни РФ (биржа закрыта). Переносы выходных меняются по годам — их можно дописать сюда.
HOLIDAYS = {"01-01", "01-02", "01-03", "01-04", "01-05", "01-06", "01-07", "01-08",
            "02-23", "03-08", "05-01", "05-09", "06-12", "11-04"}


def is_trading_day(d):
    return d.weekday() < 5 and f"{d:%m-%d}" not in HOLIDAYS


def next_trading_day(d):
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d
