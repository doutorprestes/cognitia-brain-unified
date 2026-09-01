import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CNPQ_URLS = [
    "https://www.cnpq.br/web/guest/chamadas-publicas",
    "https://www.cnpq.br/web/guest/chamadas-publicas?detalha=chamadaDivulgada&filtro=abertas",
]


def fetch_cnpq_opportunities():
    """
    Scrapes CNPq calls for proposals.
    Uses Selenium to render JavaScript content.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    for url in CNPQ_URLS:
        opts = Options()
        opts.headless = True
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            driver.get(url)
            driver.implicitly_wait(15)
            html = driver.page_source
            break
        except Exception as e:
            print(f"[CNPq] Error with {url}: {e}")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            continue
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    if not html:
        print("[CNPq] Could not fetch any URL")
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []

    links = soup.select("a[href*='chamadaDivulgada'], a.titulo, a[href*='chamadas']")
    seen_titles = set()
    today = datetime.today().date()

    for link in links:
        title = link.get_text(strip=True)
        href = link.get("href", "")

        if len(title) < 20 or title in seen_titles:
            continue

        if any(skip in title.lower() for skip in ["login", "início", "home", "menu", "resultado"]):
            continue

        seen_titles.add(title)

        if href and not href.startswith("http"):
            href = urljoin(url, href)

        date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", title)
        deadline = None
        if date_match:
            try:
                deadline = datetime.strptime(f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}", "%d/%m/%Y").date()
            except ValueError:
                pass

        if deadline and deadline < today:
            continue

        items.append({
            "title": title,
            "date": deadline.strftime("%d/%m/%Y") if deadline else "",
            "link": href,
            "snippet": "",
            "source": "CNPq"
        })

    print(f"[CNPq] Found {len(items)} open calls")
    return items
