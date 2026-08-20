"""
Crawler - V1.

For one business:
  1. fetch the homepage (try https, fall back to http once on a
     connection-level failure only)
  2. if the homepage failed, stop - there's nothing to follow
  3. if it succeeded, extract readable text + internal links
  4. pick a small number of links that look like about/contact/
     services/team/booking pages (the "crawl budget")
  5. fetch each of those too

This module does NOT touch the database - it just fetches and returns
results. Saving to Postgres and updating business status happens in
run_crawl.py. Keeping fetch logic separate from persistence means we
can test crawl_business() against a real URL without a database at all.
"""

import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "HOODBot/0.1 (prospect research; contact: you@example.com)"
MIN_BODY_LENGTH = 500  # below this, treat the page as not useful
MAX_FOLLOWED_LINKS = 4  # crawl budget: homepage + at most this many more pages
DELAY_BETWEEN_REQUESTS_SECONDS = 1  # politeness delay within one business's pages

RELEVANT_LINK_KEYWORDS = [
    "about", "contact", "service", "team", "book", "pricing", 
    "staff", "leadership", "reach", "get-in-touch"
]


@dataclass
class PageResult:
    url: str
    status_code: int | None
    text: str | None
    links_found: list[str] = field(default_factory=list)
    page_title: str | None = None
    meta_description: str | None = None
    mailto_emails: list[str] = field(default_factory=list)
    tel_hrefs: list[str] = field(default_factory=list)
    error: str | None = None
    failure_type: str | None = None  # 'transient' | 'permanent' | None (None = success)


def fetch_page(url: str) -> PageResult:
    """Fetches and parses one page. Always returns a PageResult - check .error."""
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        return PageResult(url=url, status_code=None, text=None, error=str(exc), failure_type="transient")
    except requests.exceptions.RequestException as exc:
        return PageResult(url=url, status_code=None, text=None, error=str(exc), failure_type="permanent")

    if response.status_code == 429 or response.status_code >= 500:
        return PageResult(
            url=url, status_code=response.status_code, text=None,
            error=f"HTTP {response.status_code}", failure_type="transient",
        )
    if response.status_code >= 400:
        return PageResult(
            url=url, status_code=response.status_code, text=None,
            error=f"HTTP {response.status_code}", failure_type="permanent",
        )

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return PageResult(
            url=url, status_code=response.status_code, text=None,
            error=f"non-HTML content-type: {content_type}", failure_type="permanent",
        )

    if len(response.text) < MIN_BODY_LENGTH:
        return PageResult(
            url=url, status_code=response.status_code, text=None,
            error="response body too short to be useful", failure_type="permanent",
        )

    soup = BeautifulSoup(response.text, "html.parser")

    page_title = soup.title.string.strip() if soup.title and soup.title.string else None

    meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    meta_description = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else None

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    readable_text = " ".join(soup.get_text(separator=" ").split())

    links = extract_internal_links(soup, base_url=url)
    mailto_emails, tel_hrefs = extract_contact_links(soup)

    return PageResult(
        url=url,
        status_code=response.status_code,
        text=readable_text,
        links_found=links,
        page_title=page_title,
        meta_description=meta_description,
        mailto_emails=mailto_emails,
        tel_hrefs=tel_hrefs,
    )


def extract_internal_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Resolves <a href> links to absolute URLs, keeps only same-domain ones."""
    base_domain = urlparse(base_url).netloc
    links = set()
    for a in soup.find_all("a", href=True):
        absolute = urljoin(base_url, a["href"])
        parsed = urlparse(absolute)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            links.add(absolute.split("#")[0])
    return list(links)


def extract_contact_links(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """
    Pulls mailto:/tel: links straight from anchor hrefs. This is more
    reliable than regex-matching visible page text, which can be
    decorated in ways that break simple pattern matching (markdown-style
    link text, icons-as-text, obfuscation tricks some templates use).
    """
    emails, phones = [], []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            address = href.split(":", 1)[1].split("?")[0].strip()
            if address:
                emails.append(address)
        elif href.lower().startswith("tel:"):
            number = href.split(":", 1)[1].strip()
            if number:
                phones.append(number)
    return emails, phones


def pick_relevant_links(links: list[str], limit: int = MAX_FOLLOWED_LINKS) -> list[str]:
    """Keeps only links whose path looks like about/contact/services/etc."""
    matches = []
    for link in links:
        path = urlparse(link).path.lower()
        if any(keyword in path for keyword in RELEVANT_LINK_KEYWORDS):
            matches.append(link)
    return matches[:limit]


def fetch_homepage(domain: str) -> PageResult:
    """
    Tries https first. If that fails at the connection level (not a 4xx,
    not a content problem - an actual connection failure), tries http
    once. This is a narrow, deliberate exception to the fetch-once rule:
    some smaller business sites still don't support https properly.
    """
    result = fetch_page(f"https://{domain}")
    if result.failure_type == "transient":
        fallback = fetch_page(f"http://{domain}")
        if fallback.error is None:
            return fallback
    return result


def crawl_business(domain: str) -> list[PageResult]:
    """
    Returns a list of PageResults. The first is always the homepage
    attempt (even if it failed). If the homepage succeeded, up to
    MAX_FOLLOWED_LINKS relevant internal pages are fetched too.
    """
    results = [fetch_homepage(domain)]

    homepage = results[0]
    if homepage.error is not None:
        return results  # no links to follow if we couldn't even read the homepage

    for link in pick_relevant_links(homepage.links_found):
        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)
        results.append(fetch_page(link))

    return results