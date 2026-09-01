import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

FAPESP_URL = "https://fapesp.br/chamadas"


def fetch_fapesp_opportunities():
    """
    Scrapes FAPESP calls for proposals.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(FAPESP_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[FAPESP] Error fetching: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    items = []

    links = soup.select("div.content a[href]")
    today = datetime.today().date()

    seen_titles = set()
    seen_hrefs = set()

    for link in links:
        title = link.get_text(strip=True)
        href = link.get("href", "")

        if len(title) < 20:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles or href in seen_hrefs:
            continue

        if "chamada" not in title_lower and "proposta" not in title_lower:
            continue

        if "@" in title or href.startswith("mailto:"):
            continue

        if not href.startswith("http"):
            continue

        seen_titles.add(title_lower)
        seen_hrefs.add(href)

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
            "source": "FAPESP"
        })

    print(f"[FAPESP] Found {len(items)} open calls")
    return items
