from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BOLSAS_EXTERIOR_URLS = [
    "https://www.gov.br/capes/pt-br/bolsas-no-exterior",
]


def fetch_bolsas_exterior():
    """
    Scrapes information about scholarships abroad from CAPES.
    Uses Selenium to handle dynamic content.
    Note: These are typically continuous programs rather than open calls with deadlines.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    items = []

    for base_url in BOLSAS_EXTERIOR_URLS:
        opts = Options()
        opts.headless = True
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            driver.get(base_url)
            driver.implicitly_wait(15)
            html = driver.page_source
        except Exception as e:
            print(f"[Bolsas Exterior] Error fetching {base_url}: {e}")
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

        soup = BeautifulSoup(html, "html.parser")
        source = "CAPES"

        links = soup.select("div.content a[href], article a[href], li a[href]")
        seen_titles = set()

        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if len(title) < 15:
                continue

            if not href or not href.startswith("http"):
                continue

            title_lower = title.lower()
            if any(s in title_lower for s in ["login", "início", "home", "menu", "acesso"]):
                continue

            if any(k in title_lower for k in ["bolsa", "mestrado", "doutorado", "pós-dout", "estágio", "swg", "swe", "pde", "gde", "sanduíche", "externo", "graduação"]):
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    items.append({
                        "title": title,
                        "date": "",
                        "link": href,
                        "snippet": f"Programa de bolsa {source} para estudo no exterior",
                        "source": f"Bolsas {source}"
                    })

            if len(items) >= 10:
                break

    print(f"[Bolsas Exterior] Found {len(items)} programs")
    return items
