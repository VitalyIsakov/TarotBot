"""Картинка расклада: три карты (оригинальный геометрический дизайн) + подписи активов."""
import math
import os
import datetime as dt
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from market import ASSETS

HERE = os.path.dirname(os.path.abspath(__file__))
F = lambda name, size: ImageFont.truetype(os.path.join(HERE, "assets", name), size)

W, H = 1280, 900
CW, CH = 300, 520
BG_TOP, BG_BOT = (14, 12, 34), (40, 18, 58)
GOLD, GOLD_DIM = (226, 186, 104), (150, 118, 62)
CARD_BG = (24, 22, 48)
GREEN, RED, GREY = (96, 210, 140), (240, 96, 96), (190, 190, 200)
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]


def _gradient():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    # звёзды
    import random
    rnd = random.Random(42)
    for _ in range(160):
        x, y, r = rnd.randrange(W), rnd.randrange(H), rnd.choice([1, 1, 1, 2])
        c = rnd.randrange(120, 230)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(c, c, c + 15 if c < 240 else c))
    return img


def _star(d, cx, cy, r_out, r_in, n, fill=None, outline=None, width=2, rot=-90):
    pts = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline, width=width)


def _symbol(d, card, cx, cy):
    s = card["suit"]
    if card["arcana"] == "major":
        for i in range(24):  # солнце-лучи
            a = math.radians(i * 15)
            r1, r2 = 62, 92 if i % 2 == 0 else 78
            d.line([(cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                    (cx + r2 * math.cos(a), cy + r2 * math.sin(a))], fill=GOLD, width=3)
        d.ellipse([cx - 52, cy - 52, cx + 52, cy + 52], outline=GOLD, width=3)
        d.ellipse([cx - 34, cy - 18, cx + 34, cy + 18], outline=GOLD, width=3)  # глаз
        d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=GOLD)
    elif s == "Жезлов":
        d.line([(cx - 40, cy + 75), (cx + 40, cy - 75)], fill=GOLD, width=10)
        for t in (0.25, 0.55):
            x, y = cx - 40 + 80 * t, cy + 75 - 150 * t
            d.polygon([(x, y - 14), (x + 14, y), (x, y + 14), (x - 14, y)], fill=GOLD)
        _star(d, cx + 40, cy - 75, 18, 7, 5, fill=GOLD)
    elif s == "Кубков":
        d.chord([cx - 55, cy - 90, cx + 55, cy + 20], 0, 180, outline=GOLD, width=4)
        d.line([(cx - 55, cy - 35), (cx + 55, cy - 35)], fill=GOLD, width=4)
        d.line([(cx, cy + 20), (cx, cy + 60)], fill=GOLD, width=6)
        d.polygon([(cx - 40, cy + 80), (cx + 40, cy + 80), (cx, cy + 58)], outline=GOLD, width=4)
    elif s == "Мечей":
        d.polygon([(cx, cy - 100), (cx + 10, cy - 80), (cx + 10, cy + 40), (cx - 10, cy + 40), (cx - 10, cy - 80)],
                  outline=GOLD, width=3)
        d.line([(cx - 45, cy + 40), (cx + 45, cy + 40)], fill=GOLD, width=8)
        d.line([(cx, cy + 40), (cx, cy + 85)], fill=GOLD, width=8)
        d.ellipse([cx - 9, cy + 82, cx + 9, cy + 100], fill=GOLD)
    else:  # Пентакли
        d.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline=GOLD, width=4)
        d.ellipse([cx - 66, cy - 66, cx + 66, cy + 66], outline=GOLD_DIM, width=2)
        _star(d, cx, cy, 62, 24, 5, outline=GOLD, width=3)


def _wrap(text, font, maxw, d):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def _card_face(card):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, CW - 1, CH - 1], 18, fill=CARD_BG, outline=GOLD, width=4)
    d.rounded_rectangle([12, 12, CW - 13, CH - 13], 12, outline=GOLD_DIM, width=2)
    f_num = F("DejaVuSerif-Bold.ttf", 34)
    d.text((CW / 2, 50), card["numeral"], font=f_num, fill=GOLD, anchor="mm")
    for x in (40, CW - 40):
        _star(d, x, 50, 8, 3, 4, fill=GOLD_DIM)
    _symbol(d, card, CW / 2, 225)
    d.line([(40, 360), (CW - 40, 360)], fill=GOLD_DIM, width=2)
    size = 28
    while True:  # ужимаем шрифт, пока самое длинное слово влезает в рамку
        f_name = F("DejaVuSerif-Bold.ttf", size)
        lines = _wrap(card["name"].upper(), f_name, CW - 60, d)
        if max(d.textlength(l, font=f_name) for l in lines) <= CW - 60 or size <= 18:
            break
        size -= 1
    y = 410 - (len(lines) - 1) * 18
    for ln in lines:
        d.text((CW / 2, y), ln, font=f_name, fill=GOLD, anchor="mm")
        y += 36
    return img


def _card_image(card):
    """Историческая карта (скан 1909 г.) в тонкой золотой раме; без файла — геометрическая заглушка."""
    path = os.path.join(HERE, "assets", "cards", card.get("image", ""))
    if not card.get("image") or not os.path.exists(path):
        return _card_face(card)
    art = Image.open(path).convert("RGB")
    pad = 8
    art = art.resize((CW - 2 * pad, CH - 2 * pad), Image.LANCZOS)
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, CW - 1, CH - 1], 14, fill=GOLD)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, art.width - 1, art.height - 1], 9, fill=255)
    img.paste(art, (pad, pad), mask)
    return img


def render(spread, market, date, out_path, handle=""):
    img = _gradient().convert("RGBA")
    d = ImageDraw.Draw(img)
    f_title = F("DejaVuSerif-Bold.ttf", 44)
    f_sub = F("DejaVuSans.ttf", 22)
    f_asset = F("DejaVuSans-Bold.ttf", 26)
    f_chg = F("DejaVuSans.ttf", 22)
    f_rev = F("DejaVuSerif-Italic.ttf", 21)

    d.text((W / 2, 62), "РАСКЛАД ТАРО НА РЫНОК", font=f_title, fill=GOLD, anchor="mm")
    d.text((W / 2, 108), f"{date.day} {MONTHS[date.month - 1]} {date.year}", font=f_sub, fill=GREY, anchor="mm")

    gap = (W - 3 * CW) / 4
    for i, (key, card) in enumerate(spread.items()):
        x = int(gap + i * (CW + gap))
        y = 220
        m = market.get(key)
        d.text((x + CW / 2, 160), ASSETS[key]["title"].split(" (")[0], font=f_asset, fill=(240, 236, 225), anchor="mm")
        if m:
            col = GREEN if m["chg_1d"] > 0 else RED if m["chg_1d"] < 0 else GREY
            d.text((x + CW / 2, 192), f"{m['close']:,.2f}".replace(",", " ") + f"   {m['chg_1d']:+.2f}%",
                   font=f_chg, fill=col, anchor="mm")
        face = _card_image(card)
        if card["reversed"]:
            face = face.rotate(180)
        glow = Image.new("RGBA", (CW + 60, CH + 60), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle([30, 30, CW + 30, CH + 30], 18, fill=(226, 186, 104, 90))
        glow = glow.filter(ImageFilter.GaussianBlur(16))
        img.alpha_composite(glow, (x - 30, y - 30))
        img.alpha_composite(face, (x, y))
        size = 24
        while d.textlength(card["name"].upper(), font=F("DejaVuSerif-Bold.ttf", size)) > CW + gap - 20:
            size -= 1
        f_name = F("DejaVuSerif-Bold.ttf", size)
        d.text((x + CW / 2, y + CH + 32), card["name"].upper(), font=f_name, fill=GOLD, anchor="mm")
        if card["reversed"]:
            d.text((x + CW / 2, y + CH + 64), "↻ перевёрнута", font=f_rev, fill=GOLD_DIM, anchor="mm")
    if handle:
        d.text((W - 24, H - 20), handle, font=f_sub, fill=GOLD_DIM, anchor="rs")
    img.convert("RGB").save(out_path, quality=92)
    return out_path
