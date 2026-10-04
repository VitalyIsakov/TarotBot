"""Генерация текста поста: LLM (Claude) + шаблонный запасной вариант."""
import os
import re
import random

from market import ASSETS

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

STYLE = """Ты — автор телеграм-канала «Таро для трейдеров»: каждое утро тянешь карты на рынок.
Персонаж: циничный рыночный мистик — наполовину гадалка, наполовину прожжённый трейдер с Мосбиржи.
Говоришь живо, дерзко и смешно, с самоиронией. Смешиваешь эзотерику и биржевой сленг
(«свечи», «стакан», «шорты сгорели», «ЦБ шепчет», «Меркурий в боковике»).

Правила:
- Первая строка — цепляющий заголовок-хук, который хочется дочитать (жирным).
- Блок на каждый актив: эмодзи + название актива, карта (и «перевёрнута», если так), 1–2 ярких предложения
  трактовки, привязанных к реальному вчерашнему движению. Шутки, но без воды.
- Если есть итоги прошлого расклада — коротко и честно признай счёт (угадали/промахнулись), с юмором.
- Даты: строку «Прогноз на …» с датами котировок код добавит под заголовком сам — не дублируй её.
  Прошлые движения и итоги называй днём недели («в пятницу индекс +0,05%»), слово «вчера» не используй:
  после выходных и праздников оно вводит в заблуждение.
- В конце — одна строка-«совет дня от карт» (афоризм, НЕ торговая рекомендация) и вопрос/призыв к реакции
  (например «ставьте 🔥 если верите картам»).
- НИКОГДА не давай прямых указаний купить/продать, целевых цен и уровней входа. Это гадание, не ИИР.
- Не упоминай реальных людей по именам.
- Формат: Telegram HTML, только теги <b> и <i>. Никакого Markdown.
- Объём: строго до 850 символов. Короче — лучше.
- Для USD/RUB: «рост» значит доллар дорожает, рубль слабеет."""


def _fmt_market(key, m):
    from market import asof, day_long
    if not m:
        return "данные недоступны"
    s = f"{m['close']:,.2f}".replace(",", " ") + f" ({m['chg_1d']:+.2f}% за день"
    if m.get("chg_5d") is not None:
        s += f", {m['chg_5d']:+.2f}% за неделю"
    return s + f"; {asof(key, m)}, то есть {day_long(m['date'])})"


def _card_line(c):
    return f"{c['name']}{' (перевёрнута)' if c['reversed'] else ''} — {c['meaning']}"


def build_prompt(day, spread, market, score, first=False):
    from market import day_long, day_short
    lines = [f"Прогноз на {day_long(day)} (торговая сессия этого дня).", "", "Расклад и последние котировки:"]
    for key, card in spread.items():
        pol = {1: "тянет вверх", -1: "тянет вниз", 0: "боковик/неясно"}[card["effective_polarity"]]
        lines.append(f"- {ASSETS[key]['title']}: {_fmt_market(key, market.get(key))}. "
                     f"Карта: {_card_line(card)}. Энергия карты: {pol}.")
    if score:
        lines += ["", f"Итоги прошлого расклада (прогноз на {day_long(score['pred_day'])}): "
                      f"угадано {score['hits']} из {score['total']}. Общая точность оракула: {score['acc_all']}."]
        for k, r in score["results"].items():
            lines.append(f"- {ASSETS[k]['title']}: карта {r['card']}{' (перевёрнута)' if r['reversed'] else ''}; "
                         f"движение {r['chg']:+.2f}% (с {day_short(r['from'])} по {day_short(r['to'])}) — "
                         f"{'угадано' if r['hit'] else 'промах'}")
        skipped = [ASSETS[k]['title'] for k in spread if k not in score["results"]]
        if skipped:
            lines.append(f"Не оценивались (новых котировок ещё не было): {', '.join(skipped)}.")
    if first:
        lines += ["", "Это самый первый пост канала: в заголовке обыграй запуск, в конце скажи, что с завтрашнего дня "
                      "оракул начинает публично вести счёт своих попаданий."]
    lines += ["", "Напиши пост."]
    return "\n".join(lines)


ALLOWED = re.compile(r"</?(b|i)>")


def sanitize(html):
    # убираем все теги кроме <b>/<i>, экранируем одиночные < >
    parts, last = [], 0
    for m in ALLOWED.finditer(html):
        parts.append(html[last:m.start()].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        parts.append(m.group(0))
        last = m.end()
    parts.append(html[last:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return "".join(parts).strip()


def _stem(word):
    w = word.lower().replace("ё", "е")
    return w[:5] if len(w) > 5 else w[:max(3, len(w) - 1)]


ASSET_MARKERS = {"IMOEX": ["мосбирж", "imoex", "индекс"], "RGBI": ["rgbi", "облигац", "офз"],
                 "USDRUB": ["usd", "доллар", "рубл"]}


def problems(text, cards=(), assets=(), min_len=300):
    """Проверка готового поста: всё ли на месте. Пустой список — пост целый."""
    low = re.sub(r"<[^>]+>", "", text).lower().replace("ё", "е")
    out = []
    if len(low) < min_len:
        out.append(f"короткий текст ({len(low)} симв.)")
    for k in assets:
        if not any(m in low for m in ASSET_MARKERS[k]):
            out.append(f"нет блока {k}")
    for c in cards:
        if not all(_stem(w) in low for w in c["name"].split()):
            out.append(f"нет карты «{c['name']}»")
    for t in ("b", "i"):
        if text.count(f"<{t}>") != text.count(f"</{t}>"):
            out.append(f"незакрытый тег <{t}>")
    return out


def generate_llm(prompt, system=None, cards=(), assets=(), min_len=300, attempts=3):
    """Генерация с проверкой: обрезанный или неполный текст перегенерируем, после 3 неудач — None."""
    import anthropic
    client = anthropic.Anthropic()
    for i in range(1, attempts + 1):
        msg = client.messages.create(model=MODEL, max_tokens=4000, system=system or STYLE,
                                     messages=[{"role": "user", "content": prompt}])
        text = sanitize("".join(b.text for b in msg.content if b.type == "text"))
        bad = problems(text, cards, assets, min_len)
        if msg.stop_reason != "end_turn":
            bad.insert(0, f"stop_reason={msg.stop_reason}")
        print(f"[writer] попытка {i}: {len(text)} симв., stop={msg.stop_reason}, "
              f"токены {msg.usage.input_tokens}/{msg.usage.output_tokens}" + (f" — ПРОБЛЕМЫ: {'; '.join(bad)}" if bad else " — ok"))
        if not bad:
            return text
    return None


HOOKS = ["Карты легли. Рынок нервно закурил.", "Утро, кофе, Таро. Стакан трепещет.",
         "Расклад дня: держитесь за свечи.", "Оракул проснулся раньше маркетмейкера."]


def generate_fallback(day, spread, market, score):
    out = [f"<b>🔮 {random.choice(HOOKS)}</b>", ""]
    for key, c in spread.items():
        a = ASSETS[key]
        out.append(f"{a['emoji']} <b>{a['title']}</b> — {c['name']}{' (перевёрнута)' if c['reversed'] else ''}")
        out.append(f"<i>{c['meaning'].split(' — ')[0].capitalize()}.</i>")
        out.append("")
    if score:
        from market import day_short
        out.append(f"📊 Расклад на {day_short(score['pred_day'])}: угадано {score['hits']} из {score['total']}. "
                   f"Точность оракула: {score['acc_all']}.")
    out.append("Ставьте 🔥 если верите картам, 🗿 если верите только стакану.")
    return "\n".join(out)


def with_dateline(text, day, market):
    """Строка с датой прогноза и датами котировок — сразу под заголовком (первой строкой поста)."""
    from market import dateline
    head, _, rest = text.partition("\n")
    return f"{head}\n{dateline(day, market)}\n\n{rest.lstrip()}" if rest.strip() else f"{head}\n{dateline(day, market)}"


def generate(day, spread, market, score, first=False):
    prompt = build_prompt(day, spread, market, score, first)
    text = None
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            text = generate_llm(prompt, STYLE, cards=list(spread.values()), assets=list(spread))
            if not text:
                print("[writer] текст так и не собрался целиком — публикуем шаблон")
        except Exception as e:
            print(f"[writer] LLM недоступна, шаблон: {e}")
    return with_dateline(text or generate_fallback(day, spread, market, score), day, market)


WEEKLY_STYLE = STYLE + """

Сегодня воскресенье — пост «Итоги недели оракула». Структура:
- Заголовок-хук про итоговую точность (жирным).
- Честный разбор: на каком активе карты были сильнее всего, на каком провалились, лучший и худший прогноз недели
  с картой и реальным движением. Самоирония приветствуется: оракул не всегда прав, и это часть шоу.
- Как рынок прошёл неделю (цифры даны).
- «Карта следующей недели» — короткая интригующая трактовка, без конкретных прогнозов по ценам.
- Призыв: поделиться постом / написать в комментариях, на какой актив вытянуть карту в следующий раз.
Объём: строго до 900 символов."""


def build_weekly_prompt(summary, week_moves, next_card):
    from market import ASSETS
    lines = [f"Неделя {summary['start']:%d.%m}–{summary['end']:%d.%m}. "
             f"Точность: {summary['acc']}% ({summary['hits']} из {summary['total']})."]
    for k, (h, t) in summary["per_asset"].items():
        lines.append(f"- {ASSETS[k]['title']}: угадано {h} из {t}; за неделю "
                     + (f"{week_moves[k]:+.2f}%" if week_moves.get(k) is not None else "нет данных"))
    for tag, x in (("Лучший прогноз", summary["best"]), ("Худший промах", summary["worst"])):
        if x:
            day, k, r = x
            lines.append(f"{tag}: {day}, {ASSETS[k]['title']}, карта {r['card']}"
                         f"{' (перевёрнута)' if r['reversed'] else ''}, факт {r['chg']:+.2f}%.")
    lines.append(f"Карта следующей недели: {_card_line(next_card)}.")
    lines.append("Напиши пост.")
    return "\n".join(lines)


def generate_weekly(summary, week_moves, next_card):
    prompt = build_weekly_prompt(summary, week_moves, next_card)
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            text = generate_llm(prompt, WEEKLY_STYLE, cards=[next_card], min_len=250)
            if text:
                return text
            print("[writer] итоги так и не собрались целиком — публикуем шаблон")
        except Exception as e:
            print(f"[writer] LLM недоступна, шаблон: {e}")
    from market import ASSETS
    out = [f"<b>📊 Итоги недели: оракул угадал {summary['hits']} из {summary['total']} ({summary['acc']}%)</b>", ""]
    for k, (h, t) in summary["per_asset"].items():
        mv = week_moves.get(k)
        out.append(f"{ASSETS[k]['emoji']} {ASSETS[k]['title']}: {h}/{t}" + (f", за неделю {mv:+.2f}%" if mv is not None else ""))
    out += ["", f"🃏 <b>Карта следующей недели — {next_card['name']}"
            f"{' (перевёрнута)' if next_card['reversed'] else ''}.</b> <i>{next_card['meaning'].split(' — ')[0].capitalize()}.</i>",
            "", "Напишите в комментариях, на какой актив вытянуть карту в следующий раз 👇"]
    return "\n".join(out)
