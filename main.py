"""Ежедневный расклад: данные → карты → итоги вчера → текст → картинка → Telegram."""
import argparse
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

import deck
import market
import render
import writer
import telegram
import weekly

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "data", "state.json")
TZ = ZoneInfo("Europe/Moscow")
# порог «боковика» в % — для карт с нейтральной энергией
FLAT = {"IMOEX": 0.5, "RGBI": 0.2, "USDRUB": 0.3}
LATE_LIMIT = dt.time(11, 0)  # после этого времени опоздавший плановый запуск расклад не публикует
DISCLAIMER = "\n\n<i>Расклад — развлекательный контент, не является индивидуальной инвестиционной рекомендацией.</i>"


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"last": None, "hits": 0, "total": 0, "history": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def score_previous(state, mkt):
    """Сверяем энергию вчерашних карт с фактическим движением с момента расклада."""
    last = state.get("last")
    if not last or last.get("scored"):
        return None
    hits, total, detail, results = 0, 0, [], {}
    for key, p in last["picks"].items():
        m = mkt.get(key)
        if not m or p.get("close") is None or m["date"] == p.get("date"):
            continue  # новых данных нет — не судим
        chg = (m["close"] / p["close"] - 1) * 100
        pol = p["polarity"]
        hit = (pol > 0 and chg > 0) or (pol < 0 and chg < 0) or (pol == 0 and abs(chg) < FLAT[key])
        hits += hit
        total += 1
        detail.append(f"{key} {chg:+.2f}% — {'✅' if hit else '❌'}")
        results[key] = {"card": p.get("card"), "reversed": p.get("reversed"), "image": p.get("image"),
                        "chg": round(chg, 3), "hit": bool(hit), "pred_day": last["day"],
                        "from": p.get("date"), "to": m["date"]}
    if not total:
        return None
    state["hits"] += hits
    state["total"] += total
    acc = f"{state['hits'] / state['total'] * 100:.0f}% ({state['hits']}/{state['total']})"
    return {"hits": hits, "total": total, "detail": "; ".join(detail), "acc_all": acc, "results": results,
            "pred_day": last["day"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не публиковать и не сохранять состояние")
    ap.add_argument("--force", action="store_true", help="публиковать даже если сегодня уже был пост")
    ap.add_argument("--weekly", action="store_true", help="выпустить итоги недели (по умолчанию — по воскресеньям)")
    ap.add_argument("--test", action="store_true",
                    help="тестовая публикация: расклад в любой день, счёт и состояние не сохраняются")
    args = ap.parse_args()

    today = (dt.date.fromisoformat(os.environ["TAROT_TODAY"]) if os.getenv("TAROT_TODAY")  # для проверок
             else dt.datetime.now(TZ).date())
    state = load_state()
    if state.get("last") and state["last"]["day"] == today.isoformat() and not args.force and not args.dry_run \
            and not args.test:
        print("Сегодня расклад уже опубликован.")
        return

    if args.weekly or (today.weekday() == 6 and not args.test):  # воскресенье — только итоги недели
        if state.get("last_weekly") == today.isoformat() and not args.force and not args.dry_run:
            print("Итоги недели уже опубликованы.")
            return
        return run_weekly(state, today, args)

    # GitHub иногда выполняет плановые запуски с опозданием на часы. Утренний прогноз днём не публикуем.
    # Ручной запуск и запуск через внешний будильник (workflow_dispatch) это ограничение не касается.
    now = dt.datetime.now(TZ)
    if os.getenv("GITHUB_EVENT_NAME") == "schedule" and now.time() > LATE_LIMIT and not args.test:
        print(f"Плановый запуск опоздал (сейчас {now:%H:%M} МСК) — прогноз не публикуем. "
              f"Если поста сегодня нет, запустите вручную.")
        return

    if args.test:  # тест в выходной/праздник показывает пост на ближайший торговый день
        day = market.next_trading_day(today)
    elif market.is_trading_day(today):
        day = today
    else:
        print("Сегодня биржа не работает — расклад не публикуем.")
        return

    mkt = market.fetch_all()
    if all(v is None for v in mkt.values()):
        sys.exit("Нет рыночных данных — пост не публикуем.")
    score = score_previous(state, mkt)

    cards = deck.draw(len(market.ASSETS))
    spread = dict(zip(market.ASSETS.keys(), cards))

    text = writer.generate(day, spread, mkt, score, first=not state.get("last")) + DISCLAIMER
    img_path = os.path.join(HERE, "data", f"spread_{today.isoformat()}.jpg")
    os.makedirs(os.path.dirname(img_path), exist_ok=True)
    render.render(spread, mkt, day, img_path, handle=os.getenv("CHANNEL_HANDLE", ""))

    print(text, f"\n\n[{len(text)} симв.] картинка: {img_path}")
    if args.dry_run:
        return

    telegram.publish(img_path, text)
    if args.test:
        os.remove(img_path)
        print("Тестовый пост опубликован, состояние не сохранено.")
        return
    state["last"] = {"day": day.isoformat(), "picks": {
        k: {"card": c["name"], "reversed": c["reversed"], "polarity": c["effective_polarity"],
            "image": c["image"], "close": (mkt[k] or {}).get("close"), "date": (mkt[k] or {}).get("date")}
        for k, c in spread.items()}}
    if score:  # история ведётся по дню прогноза
        state["history"] = (state.get("history", []) + [{"day": score["pred_day"], "results": score["results"]}])[-120:]
    save_state(state)
    os.remove(img_path)
    print("Опубликовано.")


def run_weekly(state, today, args):
    mkt = market.fetch_all()
    score = score_previous(state, mkt)  # сначала сверяем пятничный расклад, чтобы он попал в итоги
    if score:
        state["history"] = (state.get("history", []) + [{"day": score["pred_day"], "results": score["results"]}])[-120:]
        state["last"]["scored"] = True
    summary = weekly.collect(state.get("history", []), today)
    if not summary:
        print("За неделю нет сверенных раскладов — итоги пропускаем.")
        if score and not args.dry_run:
            save_state(state)
        return
    moves = {k: (m or {}).get("chg_5d") for k, m in mkt.items()}
    next_card = deck.draw(1, reversal_chance=0.3)[0]
    text = writer.generate_weekly(summary, moves, next_card) + DISCLAIMER
    img_path = os.path.join(HERE, "data", f"week_{today.isoformat()}.jpg")
    os.makedirs(os.path.dirname(img_path), exist_ok=True)
    weekly.render_week(summary, moves, next_card, today, img_path, handle=os.getenv("CHANNEL_HANDLE", ""))
    print(text, f"\n\n[{len(text)} симв.] картинка: {img_path}")
    if args.dry_run:
        return
    telegram.publish(img_path, text)
    state["last_weekly"] = today.isoformat()
    save_state(state)
    os.remove(img_path)
    print("Итоги недели опубликованы.")


if __name__ == "__main__":
    main()
