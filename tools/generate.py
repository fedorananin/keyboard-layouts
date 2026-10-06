#!/usr/bin/env python3
"""Regenerate the keyboard pictures and the symbol tables from the .keylayout files.

    python3 tools/generate.py

Reads   fedr.me keyboard.bundle/Contents/Resources/*.keylayout
Writes  images/<layout>-light.png, images/<layout>-dark.png
        the blocks between <!-- BEGIN ... --> / <!-- END ... --> in README.md and README.ru.md

Only the standard library is needed. The pictures are rendered with headless
Google Chrome (or Chromium / Edge); without it the tables are still updated.
"""

import html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "fedr.me keyboard.bundle" / "Contents" / "Resources"
IMAGES = ROOT / "images"

# code, file prefix, flag icon
LAYOUTS = [
    ("EN", "en", "usa.png"),
    ("RU", "ru", "russia.png"),
    ("UA", "ua", "ukraine.png"),
    ("KA", "ka", "georgia.png"),
]

BASE, SHIFT, OPTION, SHIFT_OPTION = 0, 1, 3, 4
SPACE = 49
ISO_KEY = 10

# macOS virtual key codes of an ANSI keyboard, row by row
ROWS = [
    [50, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24],
    [12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30, 42],
    [0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39],
    [6, 7, 8, 9, 11, 45, 46, 43, 47, 44],
]
KEYCAPS = dict(zip(
    [code for row in ROWS for code in row],
    "`1234567890-=" "QWERTYUIOP[]\\" "ASDFGHJKL;'" "ZXCVBNM,./",
))
KEYCAPS[SPACE] = "Space"
KEY_ORDER = [code for row in ROWS for code in row] + [SPACE]


def parse(path):
    """Return {keyMap index: {key code: output}} for a .keylayout file."""
    text = path.read_text(encoding="utf-8")
    maps = {}
    for key_map in re.finditer(r'<keyMap index="(\d+)">(.*?)</keyMap>', text, re.S):
        keys = {}
        for key in re.finditer(r'<key code="(\d+)" output="([^"]*)"', key_map.group(2)):
            keys[int(key.group(1))] = html.unescape(key.group(2))
        maps[int(key_map.group(1))] = keys
    return maps


# --------------------------------------------------------------------------- #
# Pictures
# --------------------------------------------------------------------------- #

PITCH = 68   # distance between the left edges of two neighbouring keys
GAP = 6
ROW_WIDTH = 14.5

THEMES = {
    "light": dict(case="#ececf0", key="#ffffff", edge="#d3d3da", ink="#1d1d1f", muted="#8a8a92",
                  opt="#0b63ce", opt_bg="#e4efff", shopt="#c2500a"),
    "dark": dict(case="#1b1c20", key="#2c2d33", edge="#42434b", ink="#f2f2f5", muted="#8d8e98",
                 opt="#6cb2ff", opt_bg="#1d3352", shopt="#ffa257"),
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: transparent; }
body { font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif; }
.case { color: var(--ink); width: %(width)dpx; height: %(height)dpx; padding: 18px 20px; background: var(--case); border-radius: 22px; }
.head { height: 34px; display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.head img { width: 30px; height: 30px; }
.head .name { font-size: 20px; font-weight: 650; }
.head .legend { margin-left: auto; display: flex; gap: 18px; font-size: 14px; font-weight: 600; }
.legend .opt { color: var(--opt); }
.legend .shopt { color: var(--shopt); }
.legend b { font-weight: 700; margin-right: 5px; }
.row { display: flex; gap: %(gap)dpx; margin-bottom: %(gap)dpx; height: %(key)dpx; }
.key { height: %(key)dpx; background: var(--key); border: 1px solid var(--edge); border-radius: 9px;
       display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; padding: 4px 7px;
       flex: none; line-height: 1; }
.key span { display: flex; align-items: center; }
.key .l { justify-content: flex-start; font-size: 16px; font-weight: 500; }
.key .single { grid-row: 1 / span 2; font-size: 20px; }
.key .r { justify-content: flex-end; font-size: 19px; font-weight: 600; }
.key .opt { color: var(--opt); }
.key .shopt { color: var(--shopt); }
.mod { display: flex; align-items: flex-end; padding: 0 8px 7px; font-size: 11px; color: var(--muted); }
.mod.right { justify-content: flex-end; }
.mod.option { background: var(--opt_bg); border-color: var(--opt); color: var(--opt); font-weight: 700; }
.space { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
         font-size: 12px; font-weight: 600; }
.arrows { display: flex; gap: %(gap)dpx; align-items: flex-end; flex: none; }
.arrows .half { height: %(half)dpx; flex: 1; display: flex; align-items: center; justify-content: center;
                padding: 0; font-size: 10px; color: var(--muted); }
.arrows .stack { flex: 1; display: flex; flex-direction: column; gap: 2px; }
"""


def width(units):
    return round(units * PITCH - GAP)


def legend_left(base, shift):
    if shift == base:
        return f'<span class="l single">{html.escape(base)}</span>'
    if base.isalpha() and base.upper() == shift:
        return f'<span class="l single">{html.escape(shift)}</span>'
    return (f'<span class="l" style="grid-area:1/1">{html.escape(shift)}</span>'
            f'<span class="l" style="grid-area:2/1">{html.escape(base)}</span>')


def key_html(maps, code):
    left = legend_left(maps[BASE].get(code, ""), maps[SHIFT].get(code, ""))
    shopt = html.escape(maps[SHIFT_OPTION].get(code, ""))
    opt = html.escape(maps[OPTION].get(code, ""))
    return (f'<div class="key" style="width:{width(1)}px">{left}'
            f'<span class="r shopt" style="grid-area:1/2">{shopt}</span>'
            f'<span class="r opt" style="grid-area:2/2">{opt}</span></div>')


def mod_html(label, units, cls=""):
    return f'<div class="key mod {cls}" style="width:{width(units)}px">{label}</div>'


def keyboard_html(name, maps, theme, flag):
    key = PITCH - GAP
    case_w = width(ROW_WIDTH) + 40
    case_h = 18 * 2 + 34 + 14 + 5 * PITCH - GAP
    css = CSS % dict(width=case_w, height=case_h, gap=GAP, key=key, half=(key - 2) // 2)
    variables = "".join(f"--{k}:{v};" for k, v in THEMES[theme].items())
    keys = [[key_html(maps, code) for code in row] for row in ROWS]
    rows = [
        keys[0] + [mod_html("delete", 1.5, "right")],
        [mod_html("tab", 1.5)] + keys[1],
        [mod_html("caps lock", 1.75)] + keys[2] + [mod_html("return", 1.75, "right")],
        [mod_html("shift", 2.25)] + keys[3] + [mod_html("shift", 2.25, "right")],
        [
            mod_html("fn", 1), mod_html("control", 1), mod_html("⌥ option", 1, "option"),
            mod_html("command", 1.25, "right"),
            f'<div class="key space" style="width:{width(5)}px">'
            '<span class="shopt">narrow no-break space</span><span class="opt">thin space</span></div>',
            mod_html("command", 1.25), mod_html("⌥ option", 1, "option"),
            f'<div class="arrows" style="width:{width(3)}px"><div class="key half">◀</div>'
            '<div class="stack"><div class="key half">▲</div><div class="key half">▼</div></div>'
            '<div class="key half">▶</div></div>',
        ],
    ]
    body = "".join(f'<div class="row">{"".join(row)}</div>' for row in rows)
    page = (f'<!doctype html><meta charset="utf-8"><style>{css}</style>'
            f'<div class="case" style="{variables}"><div class="head">'
            f'<img src="{flag.as_uri()}"><span class="name">{html.escape(name)}</span>'
            '<span class="legend"><span class="opt"><b>⌥</b>Option + key</span>'
            '<span class="shopt"><b>⇧ ⌥</b>Shift + Option + key</span></span></div>'
            f'{body}</div>')
    return page, case_w, case_h


def find_browser():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("chromium") or "", shutil.which("google-chrome") or "",
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def screenshot(browser, source, target, w, h, profile):
    target.unlink(missing_ok=True)
    chrome = subprocess.Popen(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--user-data-dir={profile}", "--default-background-color=00000000",
         "--force-device-scale-factor=2", f"--window-size={w},{h}",
         f"--screenshot={target}", source.as_uri()],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Chrome does not always quit after taking the screenshot, so wait for the file instead
    deadline = time.monotonic() + 60
    while chrome.poll() is None and time.monotonic() < deadline:
        if target.exists() and target.stat().st_size:
            time.sleep(0.5)
            break
        time.sleep(0.2)
    if chrome.poll() is None:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
    if not (target.exists() and target.stat().st_size):
        sys.exit(f"Chrome did not render {target.name}")


def render_images(layouts):
    browser = find_browser()
    if not browser:
        print("Chrome not found, pictures are not regenerated", file=sys.stderr)
        return
    IMAGES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for code, prefix, flag in LAYOUTS:
            for theme in THEMES:
                page, w, h = keyboard_html(f"{code} (fedr.me)", layouts[code], theme, ROOT / "icons" / flag)
                source = Path(tmp) / f"{prefix}-{theme}.html"
                source.write_text(page, encoding="utf-8")
                target = IMAGES / f"{prefix}-{theme}.png"
                screenshot(browser, source, target, w, h, Path(tmp) / f"profile-{prefix}-{theme}")
                print("wrote", target.relative_to(ROOT))


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #

CATEGORIES = [
    ("quotes", "Quotation marks", "Кавычки"),
    ("typo", "Dashes, punctuation and spaces", "Тире, пунктуация и пробелы"),
    ("money", "Currencies", "Валюты"),
    ("math", "Math and units", "Математика и единицы измерения"),
    ("marks", "Arrows and marks", "Стрелки и значки"),
    ("legal", "Legal signs", "Правовые знаки"),
    ("ascii", "ASCII symbols and letters", "ASCII-символы и буквы"),
]

# character: (category, English name, Russian name), in the order of the tables
SYMBOLS = {
    "«": ("quotes", "Left guillemet", "Левая «ёлочка»"),
    "»": ("quotes", "Right guillemet", "Правая «ёлочка»"),
    "„": ("quotes", "Low double quotation mark", "Нижняя двойная «лапка»"),
    "“": ("quotes", "Left double quotation mark", "Верхняя двойная «лапка» (вид 66)"),
    "”": ("quotes", "Right double quotation mark", "Верхняя двойная кавычка (вид 99)"),
    "‚": ("quotes", "Low single quotation mark", "Нижняя одинарная кавычка"),
    "‘": ("quotes", "Left single quotation mark", "Верхняя одинарная кавычка (вид 6)"),
    "’": ("quotes", "Right single quotation mark, apostrophe", "Одинарная кавычка (вид 9), апостроф"),
    "‹": ("quotes", "Single left guillemet", "Левая одинарная «ёлочка»"),
    "›": ("quotes", "Single right guillemet", "Правая одинарная «ёлочка»"),

    "—": ("typo", "Em dash", "Длинное тире"),
    "–": ("typo", "En dash", "Короткое тире"),
    "…": ("typo", "Ellipsis", "Многоточие"),
    "•": ("typo", "Bullet", "Буллит"),
    "⁃": ("typo", "Hyphen bullet", "Буллит-дефис"),
    "·": ("typo", "Middle dot", "Точка по центру (интерпункт)"),
    "¡": ("typo", "Inverted exclamation mark", "Перевёрнутый восклицательный знак"),
    "¿": ("typo", "Inverted question mark", "Перевёрнутый вопросительный знак"),
    "§": ("typo", "Section sign", "Параграф"),
    "¶": ("typo", "Pilcrow", "Знак абзаца"),
    "†": ("typo", "Dagger", "Крестик (даггер)"),
    "‡": ("typo", "Double dagger", "Двойной крестик"),
    "\u2009": ("typo", "Thin space", "Тонкий пробел (тонкая шпация)"),
    "\u202f": ("typo", "Narrow no-break space", "Узкий неразрывный пробел"),

    "$": ("money", "Dollar", "Доллар"),
    "€": ("money", "Euro", "Евро"),
    "£": ("money", "Pound sterling", "Фунт стерлингов"),
    "¥": ("money", "Yen, yuan", "Иена, юань"),
    "¢": ("money", "Cent", "Цент"),
    "₽": ("money", "Russian ruble", "Российский рубль"),
    "₴": ("money", "Ukrainian hryvnia", "Украинская гривна"),
    "₾": ("money", "Georgian lari", "Грузинский лари"),
    "֏": ("money", "Armenian dram", "Армянский драм"),
    "₸": ("money", "Kazakhstani tenge", "Казахстанский тенге"),
    "₼": ("money", "Azerbaijani manat", "Азербайджанский манат"),
    "₺": ("money", "Turkish lira", "Турецкая лира"),
    "₪": ("money", "Israeli new shekel", "Израильский шекель"),
    "₹": ("money", "Indian rupee", "Индийская рупия"),
    "₩": ("money", "Korean won", "Корейская вона"),
    "₱": ("money", "Philippine peso", "Филиппинское песо"),
    "฿": ("money", "Thai baht", "Тайский бат"),
    "₫": ("money", "Vietnamese dong", "Вьетнамский донг"),
    "₭": ("money", "Lao kip", "Лаосский кип"),
    "₮": ("money", "Mongolian tugrik", "Монгольский тугрик"),
    "₦": ("money", "Nigerian naira", "Нигерийская найра"),
    "₵": ("money", "Ghanaian cedi", "Ганский седи"),
    "₲": ("money", "Paraguayan guarani", "Парагвайский гуарани"),
    "₡": ("money", "Colón", "Колон"),
    "ƒ": ("money", "Florin; function sign", "Флорин; знак функции"),
    "₿": ("money", "Bitcoin", "Биткоин"),
    "Ξ": ("money", "Greek capital Xi (Ethereum)", "Греческая кси (Ethereum)"),
    "Ł": ("money", "L with stroke (Litecoin)", "L со штрихом (Litecoin)"),

    "≠": ("math", "Not equal to", "Не равно"),
    "≈": ("math", "Almost equal to", "Приблизительно равно"),
    "±": ("math", "Plus-minus", "Плюс-минус"),
    "−": ("math", "Minus", "Минус"),
    "×": ("math", "Multiplication sign", "Знак умножения"),
    "÷": ("math", "Division sign", "Знак деления"),
    "≤": ("math", "Less than or equal to", "Меньше или равно"),
    "≥": ("math", "Greater than or equal to", "Больше или равно"),
    "∞": ("math", "Infinity", "Бесконечность"),
    "√": ("math", "Square root", "Квадратный корень"),
    "∑": ("math", "Summation", "Сумма"),
    "∪": ("math", "Union", "Объединение"),
    "π": ("math", "Pi", "Пи"),
    "µ": ("math", "Micro sign", "Микро"),
    "°": ("math", "Degree", "Градус"),
    "′": ("math", "Prime (minutes, feet)", "Штрих (минуты, футы)"),
    "″": ("math", "Double prime (seconds, inches)", "Двойной штрих (секунды, дюймы)"),
    "‰": ("math", "Per mille", "Промилле"),
    "⌀": ("math", "Diameter", "Диаметр"),
    "¹": ("math", "Superscript 1", "Верхний индекс 1"),
    "²": ("math", "Superscript 2", "Верхний индекс 2"),
    "³": ("math", "Superscript 3", "Верхний индекс 3"),
    "⁴": ("math", "Superscript 4", "Верхний индекс 4"),
    "⁵": ("math", "Superscript 5", "Верхний индекс 5"),
    "⁶": ("math", "Superscript 6", "Верхний индекс 6"),
    "⁷": ("math", "Superscript 7", "Верхний индекс 7"),
    "⁸": ("math", "Superscript 8", "Верхний индекс 8"),
    "⁹": ("math", "Superscript 9", "Верхний индекс 9"),
    "⁰": ("math", "Superscript 0", "Верхний индекс 0"),

    "←": ("marks", "Left arrow", "Стрелка влево"),
    "→": ("marks", "Right arrow", "Стрелка вправо"),
    "↑": ("marks", "Up arrow", "Стрелка вверх"),
    "↓": ("marks", "Down arrow", "Стрелка вниз"),
    "✓": ("marks", "Check mark", "Галочка"),
    "✗": ("marks", "Ballot X", "Крестик"),
    "★": ("marks", "Black star", "Чёрная звезда"),
    "☆": ("marks", "White star", "Белая звезда"),
    "✱": ("marks", "Heavy asterisk", "Жирная звёздочка"),

    "©": ("legal", "Copyright", "Знак авторского права"),
    "®": ("legal", "Registered trademark", "Зарегистрированный товарный знак"),
    "™": ("legal", "Trademark", "Товарный знак"),
    "℗": ("legal", "Sound recording copyright", "Знак прав на фонограмму"),

    "@": ("ascii", "At sign", "Собака"),
    "#": ("ascii", "Number sign", "Решётка"),
    "[": ("ascii", "Left square bracket", "Левая квадратная скобка"),
    "]": ("ascii", "Right square bracket", "Правая квадратная скобка"),
    "{": ("ascii", "Left curly bracket", "Левая фигурная скобка"),
    "}": ("ascii", "Right curly bracket", "Правая фигурная скобка"),
    "ґ": ("ascii", "Ukrainian letter ґ", "Украинская буква ґ"),
    "Ґ": ("ascii", "Ukrainian letter Ґ", "Украинская буква Ґ"),
}

INVISIBLE = {"\u2009": "U+2009", "\u202f": "U+202F"}
HEADERS = {
    "en": ("Symbol", "Name", "Keys", "Unicode"),
    "ru": ("Символ", "Название", "Клавиши", "Юникод"),
}


def md(text):
    """Escape a string for a Markdown table cell."""
    return "".join(f"&#{ord(ch)};" if ch in "\\`*_[]{}<>#$@|~'\"" else ch for ch in text)


def kbd(code, lang, layouts):
    cap = KEYCAPS[code]
    if lang == "ru" and code != SPACE:
        cyrillic = layouts["RU"][SHIFT].get(code, "")
        if cyrillic.isalpha():
            cap = f"{cap} {cyrillic}"
    if code == SPACE and lang == "ru":
        cap = "Пробел"
    return f"<kbd>{md(cap)}</kbd>"


def combo(layer, code, lang, layouts):
    mods = "<kbd>⌥</kbd>" if layer == OPTION else "<kbd>⇧</kbd><kbd>⌥</kbd>"
    return mods + kbd(code, lang, layouts)


def collect(layouts):
    """{character: {(layer, key code): [layout codes]}}"""
    found = {}
    for name, *_ in LAYOUTS:
        for layer in (OPTION, SHIFT_OPTION):
            for code in KEY_ORDER:
                char = layouts[name][layer].get(code)
                if char:
                    found.setdefault(char, {}).setdefault((layer, code), []).append(name)
    return found


def keys_cell(places, lang, layouts):
    if len(places) == 1 and len(next(iter(places.values()))) == len(LAYOUTS):
        (layer, code), = places
        return combo(layer, code, lang, layouts)
    return "<br>".join(f"{combo(layer, code, lang, layouts)} — {', '.join(names)}"
                       for (layer, code), names in places.items())


def symbols_block(layouts, lang):
    found = collect(layouts)
    unknown = sorted(set(found) - set(SYMBOLS))
    if unknown:
        sys.exit("Add these characters to SYMBOLS in tools/generate.py: "
                 + " ".join(f"{c} (U+{ord(c):04X})" for c in unknown))
    out = []
    for category, title_en, title_ru in CATEGORIES:
        out += [f"### {title_ru if lang == 'ru' else title_en}", "",
                "| " + " | ".join(HEADERS[lang]) + " |", "| :---: | --- | --- | --- |"]
        for char, (cat, name_en, name_ru) in SYMBOLS.items():
            if cat != category or char not in found:
                continue
            shown = "" if char in INVISIBLE else md(char)
            out.append(f"| {shown} | {name_ru if lang == 'ru' else name_en} | "
                       f"{keys_cell(found[char], lang, layouts)} | `U+{ord(char):04X}` |")
        out.append("")
    return "\n".join(out).rstrip()


def differences_block(layouts, lang):
    names = [name for name, *_ in LAYOUTS]
    out = ["| " + ("Клавиши" if lang == "ru" else "Keys") + " | " + " | ".join(names) + " |",
           "| --- |" + " :---: |" * len(names)]
    for code in KEY_ORDER:
        for layer in (OPTION, SHIFT_OPTION):
            chars = [layouts[name][layer].get(code, "") for name in names]
            if len(set(chars)) > 1:
                out.append(f"| {combo(layer, code, lang, layouts)} | " + " | ".join(md(c) for c in chars) + " |")
    return "\n".join(out)


def update_readme(path, blocks):
    text = path.read_text(encoding="utf-8")
    for marker, content in blocks.items():
        pattern = re.compile(rf"(<!-- BEGIN {marker} -->\n).*?(<!-- END {marker} -->)", re.S)
        if not pattern.search(text):
            sys.exit(f"{path.name}: marker {marker} not found")
        text = pattern.sub(lambda m: m.group(1) + content + "\n" + m.group(2), text)
    path.write_text(text, encoding="utf-8")
    print("updated", path.relative_to(ROOT))


def main():
    layouts = {code: parse(RESOURCES / f"{code} (fedr.me).keylayout") for code, *_ in LAYOUTS}
    for lang, readme in (("en", "README.md"), ("ru", "README.ru.md")):
        update_readme(ROOT / readme, {
            "SYMBOLS": symbols_block(layouts, lang),
            "DIFFERENCES": differences_block(layouts, lang),
        })
    render_images(layouts)


if __name__ == "__main__":
    main()
