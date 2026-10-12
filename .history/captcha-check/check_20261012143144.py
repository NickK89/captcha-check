from playwright.sync_api import sync_playwright
import re

# ─────────────────────────────────────────────────────────────
# СПИСОК САЙТОВ — заполните своими
# ─────────────────────────────────────────────────────────────
with open("urls.txt", "r", encoding="utf-8") as f:
    URLS = [line.strip() for line in f if line.strip()]


# ─────────────────────────────────────────────────────────────
# 1. ВИДИМАЯ КАПЧА — селекторы элементов
# ─────────────────────────────────────────────────────────────
VISIBLE_SELECTORS = [
    # reCAPTCHA v2 (чекбокс)
    ("reCAPTCHA v2 (чекбокс)", "iframe[src*='recaptcha/api2/anchor']"),
    ("reCAPTCHA (iframe)",     "iframe[src*='google.com/recaptcha']"),
    ("reCAPTCHA (div)",        "div.g-recaptcha"),
    # hCaptcha
    ("hCaptcha (iframe)",      "iframe[src*='hcaptcha.com']"),
    ("hCaptcha (div)",         "div.h-captcha"),
    # Cloudflare Turnstile
    ("Cloudflare Turnstile",   "div.cf-turnstile"),
    ("Cloudflare Turnstile (iframe)", "iframe[src*='challenges.cloudflare.com']"),
    # Cloudflare Challenge (страница «Checking your browser»)
    ("Cloudflare Challenge",   "div#challenge-running, div#cf-challenge-running"),
    # Картинка-капча
    ("Картинка captcha",       "img[src*='captcha' i]"),
    # Форма с вводом капчи
    ("Поле ввода captcha",     "input[name*='captcha' i], input[id*='captcha' i]"),
    # Общие селекторы
    ("Элемент с 'captcha'",    "[id*='captcha' i], [class*='captcha' i]"),
]


# ─────────────────────────────────────────────────────────────
# 2. НЕВИДИМАЯ КАПЧА — косвенные признаки (без сетевых запросов)
# ─────────────────────────────────────────────────────────────
INVISIBLE_SELECTORS = [
    # Бейдж reCAPTCHA — есть и у v2 invisible, и у v3
    ("Бейдж reCAPTCHA (.grecaptcha-badge)", ".grecaptcha-badge"),
    # Скрытое поле для токена reCAPTCHA
    ("Скрытое поле g-recaptcha-response",   "textarea#g-recaptcha-response, [name='g-recaptcha-response']"),
    # Скрытое поле для токена hCaptcha
    ("Скрытое поле h-captcha-response",     "textarea[name='h-captcha-response'], [name='h-captcha-response']"),
    # Скрытое поле Turnstile
    ("Скрытое поле cf-turnstile-response",  "[name='cf-turnstile-response']"),
]


# ─────────────────────────────────────────────────────────────
# 3. ТЕКСТОВЫЕ ПРИЗНАКИ
# ─────────────────────────────────────────────────────────────
TEXT_PATTERNS = [
    (r"\bcaptcha\b",                    "текст: captcha"),
    (r"\bкапча\b",                      "текст: капча"),
    (r"я не робот|i'?m not a robot",    "текст: 'я не робот'"),
    (r"подтвердите.{0,20}робот",        "текст: 'подтвердите, что вы не робот'"),
    (r"checking your browser",          "текст: 'Checking your browser'"),
    (r"verify.{0,20}human",             "текст: 'verify you are human'"),
    (r"защита от ботов|bot protection", "текст: 'защита от ботов'"),
]


# ─────────────────────────────────────────────────────────────
# 4. СЕЛЕКТОРЫ КНОПОК для клика (ищем капчу после отправки формы)
# ─────────────────────────────────────────────────────────────
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
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────
def find_elements(page, selectors):
    """Возвращает список найденных подписей для селекторов."""
    found = []
    for label, sel in selectors:
        try:
            els = page.query_selector_all(sel)
            # Отфильтровываем по-настоящему видимые (для VISIBLE)
            if els:
                visible = [e for e in els if e.is_visible()]
                if visible:
                    found.append(f"{label}  ({len(visible)} шт.)")
                elif els:
                    # элемент есть, но скрыт — тоже полезно знать
                    found.append(f"{label}  (скрыт, {len(els)} шт.)")
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
    """Пытается кликнуть по кнопке отправки, чтобы спровоцировать капчу."""
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
    print(f"\n─── {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        visible   = find_elements(page, VISIBLE_SELECTORS)
        invisible = find_elements(page, INVISIBLE_SELECTORS)
        text_hits = find_text(page, TEXT_PATTERNS)

        # Проверка "на лету" — клик по кнопке
        clicked = try_click_button(page)
        after_click_visible = []
        after_click_text    = []
        if clicked:
            after_click_visible = find_elements(page, VISIBLE_SELECTORS)
            after_click_text    = find_text(page, TEXT_PATTERNS)

        # ── Вывод ─────────────────────────────────────────────
        if visible:
            print("  ❌ ВИДИМАЯ КАПЧА:")
            for v in visible:
                print(f"       • {v}")
        elif invisible:
            print("  🟡 НЕВИДИМАЯ КАПЧА (есть признаки):")
            for v in invisible:
                print(f"       • {v}")
        elif text_hits:
            print("  ❓ ВОЗМОЖНО КАПЧА (по тексту):")
            for t in text_hits:
                print(f"       • {t}")
        else:
            print("  ✅ Капча не обнаружена")

        # Дополнительная информация
        if invisible and not visible:
            # Уточняем, видимая она или нет — по бейджу сложно, но токен нам поможет
            for v in invisible:
                print(f"       · {v}")
        if text_hits and (visible or invisible):
            for t in text_hits:
                print(f"       · {t}")

        if clicked:
            if after_click_visible and not visible:
                print(f"  ⚠️  ПОСЛЕ КЛИКА появилась капча ({clicked}):")
                for v in after_click_visible:
                    print(f"       • {v}")
            elif after_click_text and not text_hits:
                print(f"  ⚠️  ПОСЛЕ КЛИКА появились признаки ({clicked}):")
                for t in after_click_text:
                    print(f"       • {t}")
            else:
                print(f"  ℹ️  Клик по кнопке ({clicked}) не спровоцировал капчу")

    except Exception as e:
        print(f"  ⚠️  ОШИБКА: {e}")


def main():
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
            check_url(page, url)
            page.close()
        browser.close()
        print("\n─── Готово.")


if __name__ == "__main__":
    main()
