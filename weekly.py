"""Воскресный пост: итоги недели оракула (прогнозы пн–пт) + карта следующей недели."""
import datetime as dt
import os
from PIL import Image, ImageDraw, ImageFilter

import render as R
from market import ASSETS

DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def collect(history, today):
    """Сверенные прогнозы текущей недели (пн–пт), по дню прогноза."""
    start = today - dt.timedelta(days=today.weekday())
    week = [h for h in history if h.get("results") and start <= dt.date.fromisoformat(h["day"]) < today]
    if not week:
        return None
    hits = sum(r["hit"] for h in week for r in h["results"].values())
    total = sum(len(h["results"]) for h in week)
    flat = [(h["day"], k, r) for h in week for k, r in h["results"].items()]
    best = max((x for x in flat if x[2]["hit"]), key=lambda x: abs(x[2]["chg"]), default=None)
    worst = max((x for x in flat if not x[2]["hit"]), key=lambda x: abs(x[2]["chg"]), default=None)
    per_asset = {k: [sum(h["results"][k]["hit"] for h in week if k in h["results"]),
                     sum(1 for h in week if k in h["results"])] for k in ASSETS}
    return {"start": start, "end": max(dt.date.fromisoformat(h["day"]) for h in week), "hits": hits, "total": total,
            "acc": round(hits / total * 100), "week": week, "best": best, "worst": worst,
            "per_asset": per_asset}


def render_week(summary, week_moves, next_card, today, out_path, handle=""):
    img = R._gradient().convert("RGBA")
    d = ImageDraw.Draw(img)
    F = R.F
    s, e = summary["start"], summary["end"]
    d.text((R.W / 2, 62), "ИТОГИ НЕДЕЛИ ОРАКУЛА", font=F("DejaVuSerif-Bold.ttf", 44), fill=R.GOLD, anchor="mm")
    d.text((R.W / 2, 108), f"{s.day} {R.MONTHS[s.month - 1]} — {e.day} {R.MONTHS[e.month - 1]} {e.year}",
           font=F("DejaVuSans.ttf", 22), fill=R.GREY, anchor="mm")

    # левая колонка: точность и таблица попаданий
    x0 = 70
    d.text((x0, 180), f"{summary['acc']}%", font=F("DejaVuSerif-Bold.ttf", 96), fill=R.GOLD, anchor="lt")
    d.text((x0 + 4, 300), f"угадано {summary['hits']} из {summary['total']} предсказаний",
           font=F("DejaVuSans.ttf", 24), fill=(236, 230, 214), anchor="lt")

    by_day = {dt.date.fromisoformat(h["day"]).weekday(): h["results"] for h in summary["week"]}
    col0, cw, y = x0 + 250, 62, 380
    f_h, f_row, f_dot = F("DejaVuSans.ttf", 20), F("DejaVuSans-Bold.ttf", 22), F("DejaVuSans-Bold.ttf", 30)
    for i in range(5):
        d.text((col0 + i * cw + cw / 2, y), DAYS[i], font=f_h, fill=R.GREY, anchor="mm")
    for j, (k, a) in enumerate(ASSETS.items()):
        yy = y + 58 + j * 60
        d.text((x0, yy), a["title"].split(" (")[0], font=f_row, fill=(236, 230, 214), anchor="lm")
        for i in range(5):
            r = by_day.get(i, {}).get(k)
            sym, col = ("●", R.GREEN) if r and r["hit"] else ("○", R.RED) if r else ("·", R.GOLD_DIM)
            d.text((col0 + i * cw + cw / 2, yy), sym, font=f_dot, fill=col, anchor="mm")
    d.line([(x0, y + 240), (col0 + 5 * cw, y + 240)], fill=R.GOLD_DIM, width=1)

    # движение рынка за неделю
    yy = y + 280
    d.text((x0, yy), "Рынок за неделю", font=F("DejaVuSans-Bold.ttf", 20), fill=R.GOLD, anchor="lm")
    for j, (k, a) in enumerate(ASSETS.items()):
        mv = week_moves.get(k)
        txt = f"{mv:+.2f}%" if mv is not None else "—"
        col = R.GREEN if mv and mv > 0 else R.RED if mv and mv < 0 else R.GREY
        d.text((x0, yy + 38 + j * 32), a["title"].split(" (")[0], font=F("DejaVuSans.ttf", 21), fill=R.GREY, anchor="lm")
        d.text((col0 + 5 * cw, yy + 38 + j * 32), txt, font=F("DejaVuSans-Bold.ttf", 21), fill=col, anchor="rm")

    # правая колонка: карта следующей недели
    cx = R.W - 70 - R.CW
    cy = 200
    d.text((cx + R.CW / 2, cy - 30), "КАРТА СЛЕДУЮЩЕЙ НЕДЕЛИ", font=F("DejaVuSans-Bold.ttf", 19), fill=R.GOLD, anchor="mm")
    face = R._card_image(next_card)
    if next_card["reversed"]:
        face = face.rotate(180)
    glow = Image.new("RGBA", (R.CW + 60, R.CH + 60), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([30, 30, R.CW + 30, R.CH + 30], 18, fill=(226, 186, 104, 90))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(16)), (cx - 30, cy - 30))
    img.alpha_composite(face, (cx, cy))
    name = next_card["name"].upper() + (" ↻" if next_card["reversed"] else "")
    d.text((cx + R.CW / 2, cy + R.CH + 32), name, font=F("DejaVuSerif-Bold.ttf", 22), fill=R.GOLD, anchor="mm")

    if handle:
        d.text((R.W - 24, R.H - 20), handle, font=F("DejaVuSans.ttf", 22), fill=R.GOLD_DIM, anchor="rs")
    img.convert("RGB").save(out_path, quality=92)
    return out_path
