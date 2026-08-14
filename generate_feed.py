import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import trafilatura
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator


BASE_URL = "https://pogonsportnet.pl"
NEWS_URL = "https://pogonsportnet.pl/aktualnosci/"
MAX_ARTICLES = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PogonSportNetRSS/1.0)"
}


def get_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def get_article_links():
    html = get_page(NEWS_URL)
    soup = BeautifulSoup(html, "html.parser")

    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a["href"])
        parsed = urlparse(href)

        if parsed.netloc not in ("pogonsportnet.pl", "www.pogonsportnet.pl"):
            continue

        path = parsed.path.rstrip("/")

        if not path.startswith("/aktualnosci/"):
            continue

        if path == "/aktualnosci":
            continue

        slug = path.replace("/aktualnosci/", "", 1)

        if not slug:
            continue

        clean_url = f"{BASE_URL}{path}/"

        if clean_url not in seen:
            seen.add(clean_url)
            links.append(clean_url)

        if len(links) >= MAX_ARTICLES:
            break

    return links


def extract_date(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = re.search(
        r"(\d{2}\.\d{2}\.\d{4})\s*\|\s*(\d{1,2}:\d{2})",
        text
    )

    if not match:
        return None

    try:
        dt = datetime.strptime(
            f"{match.group(1)} {match.group(2)}",
            "%d.%m.%Y %H:%M"
        )

        return dt.replace(tzinfo=ZoneInfo("Europe/Warsaw"))

    except ValueError:
        return None


def get_article(url):
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")

    if not h1:
        return None

    title = h1.get_text(" ", strip=True)

    content = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_images=True,
        include_formatting=True,
        favor_precision=True,
        url=url
    )

    if not content:
        content = trafilatura.extract(
            html,
            output_format="html",
            include_links=True,
            include_formatting=True,
            url=url
        )

    if not content:
        return None

    return {
        "title": title,
        "url": url,
        "content": content,
        "date": extract_date(html)
    }


def build_feed():
    links = get_article_links()

    print(f"Znaleziono {len(links)} artykulow.")

    articles = []

    for number, url in enumerate(links, 1):
        print(f"[{number}/{len(links)}] {url}")

        try:
            article = get_article(url)

            if article:
                articles.append(article)

        except Exception as error:
            print(f"Blad dla {url}: {error}")

        time.sleep(0.5)

    fg = FeedGenerator()

    fg.id(NEWS_URL)
    fg.title("Pogon SportNet - Full Text RSS")
    fg.link(href=NEWS_URL, rel="alternate")
    fg.description(
        "Pelnotekstowy RSS aktualnosci z Pogon SportNet."
    )
    fg.language("pl")

    for article in reversed(articles):
        entry = fg.add_entry()

        entry.id(article["url"])
        entry.title(article["title"])
        entry.link(href=article["url"])

        entry.description(article["content"])
        entry.content(article["content"], type="html")

        if article["date"]:
            entry.pubDate(article["date"])

    fg.rss_file("feed.xml", pretty=True)

    print(
        f"Gotowe. Feed zawiera {len(articles)} artykulow."
    )


if __name__ == "__main__":
    build_feed()
