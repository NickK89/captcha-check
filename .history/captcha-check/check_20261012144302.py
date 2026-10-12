from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
from collections import defaultdict
import re

# ─────────────────────────────────────────────────────────────
# СПИСОК САЙТОВ — читаем из urls.txt, если он есть, иначе из списка
# ─────────────────────────────────────────────────────────────
try:
    with open("urls.txt", "r", encoding="utf-8") as f:
        URLS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    URLS = [
        "https://example.com",
        "https://www.google.com/recaptcha/api2/demo",
    ]


# ─────────────────────────────────────────────────────────────
# ВИДИМАЯ КАПЧА
# ─────────────────────────────────────────────────────────────
VISIBLE_SELECTORS = [
    ("reCAPTCHA v2 (чекбокс)", "iframe[src*='recaptcha/api2/anchor']"),
    ("reCAPTCHA (iframe)",     "iframe[src*='google.com/recaptcha']"),
    ("reCAPTCHA (div)",        "div.g-recaptcha"),
    ("hCaptcha (iframe)",      "iframe[src*='hcaptcha.com']"),
    ("hCaptcha (div)",         "div.h-captcha"),
    ("Cloudflare Turnstile",   "div.cf-turnstile"),
    ("Cloudflare Turnstile (iframe)", "iframe[src*='challenges.cloudflare.com']"),
    ("Cloudflare Challenge",   "div#challenge-running, div#cf-challenge-running"),
    ("Картинка captcha",       "img[src*='captcha' i]"),
    ("Поле ввода captcha",     "input[name*='captcha' i], input[id*='captcha' i]"),
    ("Элемент с 'captcha'",    "[id*='captcha' i], [class*='captcha' i]"),
]

# ─────────────────────────────────────────────────────────────
# НЕВИДИМАЯ КАПЧА
# ─────────────────────────────────────────────────────────────
INVISIBLE_SELECTORS = [
    ("reCAPTCHA v3 (бейдж)",             ".grecaptcha-badge"),
    ("reCAPTCHA (скрытый токен)",        "textarea#g-recaptcha-response, [name='g-recaptcha-response']"),
    ("hCaptcha (скрытый токен)",         "textarea[name='h-captcha-response'], [name='h-captcha-response']"),
    ("Turnstile (скрытый токен)",        "[name='cf-turnstile-response']"),
]

# ─────────────────────────────────────────────────────────────
# ТЕКСТОВЫЕ ПРИЗНАКИ
# ─────────────────────────────────────────────────────────────
TEXT_PATTERNS = [
    (r"\bcaptcha\b",                    "упоминание 'captcha'"),
    (r"\bкапча\b",                      "упоминание 'капча'"),
    (r"я не робот|i'?m not a robot",    "'я не робот'"),
    (r"подтвердите.{0,20}робот",        "'подтвердите, что вы не робот'"),
    (r"checking your browser",          "'Checking your browser'"),
    (r"verify.{0,20}human",             "'verify you are human'"),
    (r"защита от ботов|bot protection", "'защита от ботов'"),
]

BUTTON_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Отправить')",
    "button:has-text('Submit')",
    "button:has-text('Отправить заявку')",
    "button:has-text('Войти')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
]


# ─────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ
# ─────────────────────────────────────────────────────────────
def find_elements(page, selectors):
    found = []
    for label, sel in selectors:
        try:
            els = page.query_selector_all(sel)
            if els:
                visible = [e for e in els if e.is_visible()]
                if visible:
                    found.append((label, len(visible)))
                else:
                    found.append((label + " (скрыт)", len(els)))
        except Exception:
            pass
    return found


def find_text(page, patterns):
    found = []
    try:
        text = page.inner_text("body")
    except Exception:
        return found
    for pat, label in patterns:
        if re.search(pat, text, re.IGNORECASE):
            found.append(label)
    return found


def try_click_button(page):
    for sel in BUTTON_SELECTORS:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click(timeout=3000)
                page.wait_for_timeout(2500)
                return sel
        except Exception:
            continue
    return None


def check_url(page, url):
    """Возвращает dict с результатом."""
    result = {
        "url": url,
        "status": "clean",   # clean | visible | invisible | text | error
        "findings": [],
        "error": None,
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        visible   = find_elements(page, VISIBLE_SELECTORS)
        invisible = find_elements(page, INVISIBLE_SELECTORS)
        text_hits = find_text(page, TEXT_PATTERNS)

        clicked = try_click_button(page)
        if clicked:
            after_visible = find_elements(page, VISIBLE_SELECTORS)
            after_text    = find_text(page, TEXT_PATTERNS)
            if after_visible and not visible:
                visible = after_visible
                result["findings"].append(f"появилась после клика ({clicked})")
            if after_text and not text_hits:
                text_hits = after_text

        if visible:
            result["status"] = "visible"
            result["findings"] = [f"{lbl} × {n}" for lbl, n in visible]
        elif invisible:
            result["status"] = "invisible"
            result["findings"] = [f"{lbl} × {n}" for lbl, n in invisible]
        elif text_hits:
            result["status"] = "text"
            result["findings"] = text_hits

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def print_result(r):
    url = r["url"]
    print(f"\n─── {url}")
    if r["status"] == "error":
        print(f"  ⚠️  ОШИБКА: {r['error']}")
    elif r["status"] == "clean":
        print("  ✅ Капча не обнаружена")
    elif r["status"] == "visible":
        print("  ❌ ВИДИМАЯ КАПЧА:")
        for f in r["findings"]:
            print(f"       • {f}")
    elif r["status"] == "invisible":
        print("  🟡 НЕВИДИМАЯ КАПЧА (признаки):")
        for f in r["findings"]:
            print(f"       • {f}")
    elif r["status"] == "text":
        print("  ❓ ВОЗМОЖНО КАПЧА (по тексту):")
        for f in r["findings"]:
            print(f"       • {f}")


def print_summary(results):
    """Печатает общий отчёт в конце."""
    total = len(results)
    by_status = defaultdict(list)
    for r in results:
        by_status[r["status"]].append(r)

    visible_count   = len(by_status["visible"])
    invisible_count = len(by_status["invisible"])
    text_count      = len(by_status["text"])
    clean_count     = len(by_status["clean"])
    error_count     = len(by_status["error"])

    print("\n" + "═" * 60)
    print("  ИТОГОВЫЙ ОТЧЁТ")
    print("═" * 60)
    print(f"  Всего проверено страниц: {total}")
    print(f"    ❌ Видимая капча:      {visible_count}")
    print(f"    🟡 Невидимая капча:    {invisible_count}")
    print(f"    ❓ Подозрение (текст): {text_count}")
    print(f"    ✅ Чисто:              {clean_count}")
    print(f"    ⚠️  Ошибок загрузки:   {error_count}")

    # Группировка по сайтам
    by_site = defaultdict(list)
    for r in results:
        domain = urlparse(r["url"]).netloc
        by_site[domain].append(r)

    if len(by_site) > 1:
        print("\n  ПО САЙТАМ:")
        for site, items in sorted(by_site.items()):
            v = sum(1 for r in items if r["status"] == "visible")
            i = sum(1 for r in items if r["status"] == "invisible")
            t = sum(1 for r in items if r["status"] == "text")
            c = sum(1 for r in items if r["status"] == "clean")
            e = sum(1 for r in items if r["status"] == "error")
            flags = []
            if v: flags.append(f"❌{v}")
            if i: flags.append(f"🟡{i}")
            if t: flags.append(f"❓{t}")
            if c: flags.append(f"✅{c}")
            if e: flags.append(f"⚠️{e}")
            print(f"    {site}  ({len(items)} стр.):  {'  '.join(flags)}")

    # Список страниц с капчей
    if visible_count:
        print("\n  ❌ СТРАНИЦЫ С ВИДИМОЙ КАПЧЕЙ:")
        for r in by_status["visible"]:
            print(f"    • {r['url']}")
            for f in r["findings"]:
                print(f"         {f}")

    if invisible_count:
        print("\n  🟡 СТРАНИЦЫ С ПРИЗНАКАМИ НЕВИДИМОЙ КАПЧИ:")
        for r in by_status["invisible"]:
            print(f"    • {r['url']}")
            for f in r["findings"]:
                print(f"         {f}")

    if text_count:
        print("\n  ❓ СТРАНИЦЫ С ПОДОЗРЕНИЕМ (по тексту):")
        for r in by_status["text"]:
            print(f"    • {r['url']}  →  {', '.join(r['findings'])}")

    if error_count:
        print("\n  ⚠️  СТРАНИЦЫ С ОШИБКАМИ:")
        for r in by_status["error"]:
            print(f"    • {r['url']}  →  {r['error'][:80]}")

    print("\n" + "═" * 60)
    print("  Готово.")
    print("═" * 60)


def main():
    print(f"Проверяю {len(URLS)} страниц(у)...")
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        for url in URLS:
            page = context.new_page()
            r = check_url(page, url)
            page.close()
            print_result(r)
            results.append(r)
        browser.close()

    print_summary(results)


if __name__ == "__main__":
    main()