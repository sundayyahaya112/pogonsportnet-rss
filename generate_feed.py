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

        if parsed.netloc not in (
            "pogonsportnet.pl",
            "www.pogonsportnet.pl"
        ):
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

        return dt.replace(
            tzinfo=ZoneInfo("Europe/Warsaw")
        )

    except ValueError:
        return None


def extract_title(soup):
    # Najpierw Open Graph - zwykle zawiera prawdziwy tytul artykulu
    og_title = soup.find(
        "meta",
        attrs={"property": "og:title"}
    )

    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

        if title and title.lower() != "aktualności":
            return title

    # Nastepnie Twitter Card
    twitter_title = soup.find(
        "meta",
        attrs={"name": "twitter:title"}
    )

    if twitter_title and twitter_title.get("content"):
        title = twitter_title["content"].strip()

        if title and title.lower() != "aktualności":
            return title

    # Dopiero potem szukamy H1
    h1_tags = soup.find_all("h1")

    for h1 in h1_tags:
        title = h1.get_text(" ", strip=True)

        if (
            title
            and title.lower() != "aktualności"
            and len(title) > 5
        ):
            return title

    # Ostateczny fallback
    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

        title = re.sub(
            r"\s*[-|]\s*Pogoń SportNet.*$",
            "",
            title,
            flags=re.IGNORECASE
        )

        if title:
            return title

    return None


def extract_main_image(soup, url):
    # Open Graph jest najlepszym kandydatem
    og_image = soup.find(
        "meta",
        attrs={"property": "og:image"}
    )

    if og_image and og_image.get("content"):
        return urljoin(
            url,
            og_image["content"].strip()
        )

    # Twitter Card jako fallback
    twitter_image = soup.find(
        "meta",
        attrs={"name": "twitter:image"}
    )

    if twitter_image and twitter_image.get("content"):
        return urljoin(
            url,
            twitter_image["content"].strip()
        )

    return None


def make_image_urls_absolute(content, article_url):
    soup = BeautifulSoup(content, "html.parser")

    for img in soup.find_all("img"):
        src = img.get("src")

        if src:
            img["src"] = urljoin(
                article_url,
                src
            )

        # Obsluga lazy-loading
        if not src:
            lazy_src = (
                img.get("data-src")
                or img.get("data-lazy-src")
            )

            if lazy_src:
                img["src"] = urljoin(
                    article_url,
                    lazy_src
                )

    for a in soup.find_all("a", href=True):
        a["href"] = urljoin(
            article_url,
            a["href"]
        )

    return str(soup)


def get_article(url):
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title(soup)

    if not title:
        print(
            f"Nie znaleziono tytulu: {url}"
        )
        return None

    main_image = extract_main_image(
        soup,
        url
    )

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
            include_images=True,
            include_formatting=True,
            url=url
        )

    if not content:
        return None

    content = make_image_urls_absolute(
        content,
        url
    )

    # Dodaj glowne zdjecie na poczatku,
    # jezeli Trafilatura go nie zachowala
    if main_image and main_image not in content:
        image_html = (
            f'<p><img src="{main_image}" '
            f'alt="{title}" /></p>'
        )

        content = image_html + content

    return {
        "title": title,
        "url": url,
        "content": content,
        "date": extract_date(html),
        "image": main_image
    }


def build_feed():
    links = get_article_links()

    print(
        f"Znaleziono {len(links)} artykulow."
    )

    articles = []

    for number, url in enumerate(
        links,
        1
    ):
        print(
            f"[{number}/{len(links)}] {url}"
        )

        try:
            article = get_article(url)

            if article:
                articles.append(article)

                print(
                    f"  Tytul: {article['title']}"
                )

                print(
                    f"  Obraz: {article['image']}"
                )

        except Exception as error:
            print(
                f"Blad dla {url}: {error}"
            )

        time.sleep(0.5)

    fg = FeedGenerator()

    fg.id(NEWS_URL)
    fg.title(
        "Pogon SportNet - Full Text RSS"
    )
    fg.link(
        href=NEWS_URL,
        rel="alternate"
    )
    fg.description(
        "Pelnotekstowy RSS aktualnosci "
        "z Pogon SportNet."
    )
    fg.language("pl")

    for article in reversed(articles):
        entry = fg.add_entry()

        entry.id(article["url"])
        entry.title(article["title"])

        entry.link(
            href=article["url"],
            rel="alternate"
        )

        entry.description(
            article["content"]
        )

        entry.content(
            article["content"],
            type="html"
        )

        if article["date"]:
            entry.pubDate(
                article["date"]
            )

        # RSS enclosure dla glownego obrazka
        if article["image"]:
            try:
                entry.enclosure(
                    article["image"],
                    0,
                    "image/jpeg"
                )
            except Exception as error:
                print(
                    "Nie udalo sie dodac "
                    f"enclosure: {error}"
                )

    fg.rss_file(
        "feed.xml",
        pretty=True
    )

    print(
        f"Gotowe. Feed zawiera "
        f"{len(articles)} artykulow."
    )


if __name__ == "__main__":
    build_feed()
