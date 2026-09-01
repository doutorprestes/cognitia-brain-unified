import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config

FINEP_URL = "https://www.finep.gov.br/chamadas-publicas"


def fetch_finep_opportunities():
    """
    Scrapes FINEP calls for proposals.
    Uses requests as primary method, falls back to Selenium if needed.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(FINEP_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[FINEP] Error fetching: {e}")
        return _fetch_finep_selenium()

    soup = BeautifulSoup(response.text, "html.parser")
    items = []

    cards = soup.select("#conteudoChamada .item")
    if not cards:
        cards = soup.select("div.chamada-item, div.item-chamada, div.resultado")

    today = datetime.today().date()

    for card in cards:
        title_elem = card.select_one("h3 a, h2 a, a.titulo, a.title")
        if not title_elem:
            continue

        title = title_elem.get_text(strip=True)
        if len(title) < 10:
            continue

        link = title_elem.get("href", "")
        if link and not link.startswith("http"):
            link = urljoin(FINEP_URL, link)

        date_elem = card.select_one("div.prazo_div, span.date, .prazo, time")
        deadline = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_text)
            if m:
                try:
                    deadline = datetime.strptime(f"{m.group(1)}/{m.group(2)}/{m.group(3)}", "%d/%m/%Y").date()
                except ValueError:
                    pass

        if deadline and deadline < today:
            continue

        snippet = date_elem.get_text(strip=True) if date_elem else ""

        items.append({
            "title": title,
            "date": deadline.strftime("%d/%m/%Y") if deadline else "",
            "link": link,
            "snippet": snippet,
            "source": "FINEP"
        })

    if not items:
        return _fetch_finep_selenium()

    print(f"[FINEP] Found {len(items)} open calls")
    return items


def _fetch_finep_selenium():
    """
    Fallback using Selenium if requests doesn't work.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("[FINEP] Selenium not available")
        return []

    opts = Options()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.get(FINEP_URL)
        driver.implicitly_wait(10)
        html = driver.page_source
    except Exception as e:
        print(f"[FINEP] Selenium error: {e}")
        return []
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    soup = BeautifulSoup(html, "html.parser")
    items = []

    cards = soup.select("#conteudoChamada .item")
    today = datetime.today().date()

    for card in cards:
        a = card.select_one("h3 > a")
        prazo_el = card.select_one("div.prazo_div")
        if not a or not prazo_el:
            continue

        title = a.get_text(strip=True)
        snippet = prazo_el.get_text(strip=True)
        m = re.search(r"(\d{2}/\d{2}/\d{4})", snippet)
        if not m:
            continue

        try:
            deadline = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        except ValueError:
            continue

        if deadline < today:
            continue

        link = urljoin(FINEP_URL, a.get("href", ""))
        items.append({
            "title": title,
            "date": m.group(1),
            "link": link,
            "snippet": snippet,
            "source": "FINEP"
        })

    print(f"[FINEP] Found {len(items)} open calls (Selenium)")
    return items
