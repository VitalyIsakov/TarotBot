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
    if not last:
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
                        "chg": round(chg, 3), "hit": bool(hit), "pred_day": last["day"]}
    if not total:
        return None
    state["hits"] += hits
    state["total"] += total
    acc = f"{state['hits'] / state['total'] * 100:.0f}% ({state['hits']}/{state['total']})"
    return {"hits": hits, "total": total, "detail": "; ".join(detail), "acc_all": acc, "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не публиковать и не сохранять состояние")
    ap.add_argument("--force", action="store_true", help="публиковать даже если сегодня уже был пост")
    ap.add_argument("--weekly", action="store_true", help="выпустить итоги недели (по умолчанию — по воскресеньям)")
    ap.add_argument("--daily", action="store_true", help="выпустить обычный расклад даже в воскресенье (для теста)")
    ap.add_argument("--test", action="store_true",
                    help="тестовая публикация: расклад в любой день, счёт и состояние не сохраняются")
    args = ap.parse_args()
    if args.test:
        args.daily = True

    today = dt.datetime.now(TZ).date()
    state = load_state()
    if state.get("last") and state["last"]["day"] == today.isoformat() and not args.force and not args.dry_run \
            and not args.test:
        print("Сегодня расклад уже опубликован.")
        return

    if (today.weekday() == 6 and not args.daily) or args.weekly:  # воскресенье — только итоги недели
        if state.get("last_weekly") == today.isoformat() and not args.force and not args.dry_run:
            print("Итоги недели уже опубликованы.")
            return
        return run_weekly(state, today, args)

    mkt = market.fetch_all()
    if all(v is None for v in mkt.values()):
        sys.exit("Нет рыночных данных — пост не публикуем.")
    score = score_previous(state, mkt)

    cards = deck.draw(len(market.ASSETS))
    spread = dict(zip(market.ASSETS.keys(), cards))

    text = writer.generate(today.strftime("%d.%m.%Y"), spread, mkt, score, first=not state.get("last")) + DISCLAIMER
    img_path = os.path.join(HERE, "data", f"spread_{today.isoformat()}.jpg")
    os.makedirs(os.path.dirname(img_path), exist_ok=True)
    render.render(spread, mkt, today, img_path, handle=os.getenv("CHANNEL_HANDLE", ""))

    print(text, f"\n\n[{len(text)} симв.] картинка: {img_path}")
    if args.dry_run:
        return

    telegram.publish(img_path, text)
    if args.test:
        os.remove(img_path)
        print("Тестовый пост опубликован, состояние не сохранено.")
        return
    state["last"] = {"day": today.isoformat(), "picks": {
        k: {"card": c["name"], "reversed": c["reversed"], "polarity": c["effective_polarity"],
            "image": c["image"], "close": (mkt[k] or {}).get("close"), "date": (mkt[k] or {}).get("date")}
        for k, c in spread.items()}}
    state["history"] = (state.get("history", []) + [{"day": today.isoformat(),
                        "results": (score or {}).get("results", {})}])[-120:]
    save_state(state)
    os.remove(img_path)
    print("Опубликовано.")


def run_weekly(state, today, args):
    summary = weekly.collect(state.get("history", []), today)
    if not summary:
        print("За неделю нет сверенных раскладов — итоги пропускаем.")
        return
    mkt = market.fetch_all()
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
