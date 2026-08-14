"""
Turns a URL into a canonical domain we can dedupe on.

V0 dedup strategy: domain only. No phone/email/name matching yet -
add that later if we actually see duplicates slip through with
different domains (e.g. abc-realty.com vs abcrealtymiami.com).
"""

from urllib.parse import urlparse


def canonical_domain(url: str | None) -> str | None:
    """
    'https://www.ABC-Realty.com/contact' -> 'abc-realty.com'
    None or empty input -> None
    """
    if not url:
        return None

    # urlparse needs a scheme to find the netloc correctly
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    return host or None
