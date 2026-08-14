"""
Extractor - V1.

Pulls a small, deterministic set of fields out of a business's saved
pages: phone, email, page title, meta description.

No AI, no judgment calls about what counts as a "service" or a
qualification signal - that's the AI audit stage downstream in n8n.
This module only pulls things unambiguously present in the HTML.
"""

import re
from dataclasses import dataclass

PHONE_PATTERN = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Catches unrendered client-side template syntax like {{agentDetails.phone}}
# or ${phone}. Some site builders inject the real contact value via
# JavaScript after page load - since V1 only fetches static HTML (no
# browser), what we see is the literal placeholder, not real data. A
# genuine phone/email never contains { or }, so this is a safe filter.
TEMPLATE_PLACEHOLDER_PATTERN = re.compile(r"[{}]")

# Domains that show up in scraped text but are never a real business
# contact email - platform boilerplate/tracking noise, not a signal.
EMAIL_DOMAIN_BLOCKLIST = {
    "example.com", "yourdomain.com", "sentry.io", "wixpress.com",
    "godaddy.com", "schema.org",
}


def is_template_placeholder(value: str) -> bool:
    return bool(TEMPLATE_PLACEHOLDER_PATTERN.search(value))


@dataclass
class ExtractedFields:
    phone: str | None
    email: str | None
    page_title: str | None
    description: str | None
    phone_source: str | None = None  # 'href' | 'text_regex' | None
    email_source: str | None = None  # 'href' | 'text_regex' | None


def find_phone(text: str) -> str | None:
    match = PHONE_PATTERN.search(text)
    return match.group(0) if match else None


def find_email(text: str) -> str | None:
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group(0)
        domain = email.split("@")[-1].lower()
        if domain not in EMAIL_DOMAIN_BLOCKLIST:
            return email
    return None


def extract_from_pages(pages) -> ExtractedFields:
    """
    pages: saved page rows for one business, homepage first (see
    db.get_pages_for_business). Takes the first match found for each
    field, checking pages in that order, and stops early once every
    field has been found.

    For phone/email, a mailto:/tel: link found on the page is always
    preferred over a regex match against the flattened visible text -
    hrefs are structured and unambiguous, whereas visible text can be
    decorated in ways that confuse a regex (e.g. markdown-style link
    text, obfuscation tricks some site templates use).
    """
    phone = email = page_title = description = None
    phone_source = email_source = None

    for page in pages:
        if email is None and page.mailto_emails:
            for candidate in page.mailto_emails.split("|"):
                if is_template_placeholder(candidate):
                    continue
                domain = candidate.split("@")[-1].lower()
                if domain not in EMAIL_DOMAIN_BLOCKLIST:
                    email = candidate
                    email_source = "href"
                    break

        if phone is None and page.tel_hrefs:
            for candidate in page.tel_hrefs.split("|"):
                if not is_template_placeholder(candidate):
                    phone = candidate
                    phone_source = "href"
                    break

        if page.text is not None:
            if phone is None:
                found = find_phone(page.text)
                if found is not None:
                    phone = found
                    phone_source = "text_regex"
            if email is None:
                found = find_email(page.text)
                if found is not None:
                    email = found
                    email_source = "text_regex"

        if page_title is None and page.page_title:
            page_title = page.page_title
        if description is None and page.meta_description:
            description = page.meta_description

        if phone and email and page_title and description:
            break

    return ExtractedFields(
        phone=phone, email=email, page_title=page_title, description=description,
        phone_source=phone_source, email_source=email_source,
    )
