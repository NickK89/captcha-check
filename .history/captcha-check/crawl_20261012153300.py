from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
import re
import sys
import time

# ─────────────────────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────────────────────
START_URL = "https://example"   # 👈 ЗДЕСЬ укажите сайт
MAX_PAGES = 100                   # максимум страниц при краулинге
OUTPUT_FILE = "urls.txt"          # куда сохранить результат
# ─────────────────────────────────────────────────────────────


def normalize(url, base):
    """Приводит ссылку к чистому виду: без якорей, без лишних параметров."""
    if not url:
        return None
    url = url.strip()
    if url.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    full = urljoin(base, url)
    full = full.split("#")[0]           # убираем якорь
    return full


def same_domain(url, domain):
    try:
        return urlparse(url).netloc.lower().replace("www.", "") == \
               domain.lower().replace("www.", "")
    except Exception:
        return False


def try_sitemap(base):
    """Пытается найти sitemap.xml и вернуть список URL из него."""
    print("→ Проверяю sitemap.xml...")
    candidates = [
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-index.xml",
        "/sitemap/sitemap.xml",
    ]

    import urllib.request
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CaptchaCheck/1.0)"}

    for path in candidates:
        url = base.rstrip("/") + path
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            if "<urlset" in content or "<sitemapindex" in content:
                print(f"   найден sitemap: {url}")
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", content, re.IGNORECASE)

                # Если это sitemapindex — там вложенные sitemap, заходим в каждый
                if "<sitemapindex" in content:
                    print(f"   это индекс из {len(locs)} вложенных sitemap, разворачиваю...")
                    all_urls = []
                    for sub in locs[:20]:  # ограничим 20 вложенными
                        try:
                            req2 = urllib.request.Request(sub, headers=headers)
                            with urllib.request.urlopen(req2, timeout=10) as r2:
                                sub_content = r2.read().decode("utf-8", errors="ignore")
                            all_urls += re.findall(r"<loc>\s*(.*?)\s*</loc>", sub_content, re.IGNORECASE)
                        except Exception as e:
                            print(f"      пропуск {sub}: {e}")
                    return all_urls
                return locs
        except Exception:
            continue

    print("   sitemap не найден")
    return []


def crawl(start_url, max_pages):
    """Обходит сайт с главной, собирая внутренние ссылки."""
    print(f"→ Краулинг {start_url} (лимит {max_pages} страниц)...")
    domain = urlparse(start_url).netloc
    visited = set()
    to_visit = [start_url]
    all_found = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(800)
                visited.add(url)
                all_found.add(url)

                # Собираем все ссылки со страницы
                links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.getAttribute('href'))"
                )
                new_count = 0
                for raw in links:
                    clean = normalize(raw, url)
                    if not clean:
                        continue
                    if not same_domain(clean, domain):
                        continue
                    if clean not in visited and clean not in to_visit:
                        to_visit.append(clean)
                        new_count += 1

                print(f"   [{len(visited)}/{max_pages}] {url}  (+{new_count} новых)")

            except Exception as e:
                print(f"   [{len(visited)}/{max_pages}] {url}  ошибка: {e}")

        browser.close()

    print(f"   обошли {len(visited)} страниц")
    return list(all_found)


def main():
    # Проверяем, что сайт начинается с http
    base = START_URL.strip()
    if not base.startswith(("http://", "https://")):
        print("❌ START_URL должен начинаться с http:// или https://")
        sys.exit(1)

    print(f"Сайт: {base}\n")

    # Шаг 1. Sitemap
    urls = try_sitemap(base)

    # Шаг 2. Если sitemap пуст — краулинг
    if not urls:
        urls = crawl(base, MAX_PAGES)

    # Чистим и дедуплицируем
    domain = urlparse(base).netloc
    clean_urls = []
    seen = set()
    for u in urls:
        u = u.strip()
        if not u or u in seen:
            continue
        if not same_domain(u, domain):
            continue
        seen.add(u)
        clean_urls.append(u)

    # Сохраняем
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for u in clean_urls:
            f.write(u + "\n")

    print(f"\n✅ Готово. Найдено {len(clean_urls)} URL.")
    print(f"   Сохранено в {OUTPUT_FILE}")
    print(f"\nПервые 10:")
    for u in clean_urls[:10]:
        print(f"   {u}")


if __name__ == "__main__":
    main()