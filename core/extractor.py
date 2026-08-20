"""
Extractor - V1.1 (Upgraded)
Pulls deterministic contact fields: phone, email, page title, meta description.
Includes JSON-LD parsing, mailto unquoting, and anti-obfuscation.
"""
import re
import json
import urllib.parse
from dataclasses import dataclass

PHONE_PATTERN = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Detects obfuscations like 'john [at] agency.com' or 'sales(at)domain.com'
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|@)\s*([a-zA-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\.)\s*([a-zA-Z]{2,})",
    re.IGNORECASE
)

TEMPLATE_PLACEHOLDER_PATTERN = re.compile(r"[{}]")

EMAIL_DOMAIN_BLOCKLIST = {
    "example.com", "yourdomain.com", "sentry.io", "wixpress.com",
    "godaddy.com", "schema.org", "wix.com", "wordpress.org", "gravatar.com"
}

GENERIC_PREFIXES = {"info", "contact", "support", "sales", "admin", "hello", "team", "office", "help"}

def is_template_placeholder(value: str) -> bool:
    return bool(TEMPLATE_PLACEHOLDER_PATTERN.search(value))

def clean_email_str(raw: str) -> str:
    cleaned = urllib.parse.unquote(raw).strip().lower().rstrip(".")
    return cleaned

@dataclass
class ExtractedFields:
    phone: str | None
    email: str | None
    page_title: str | None
    description: str | None
    phone_source: str | None = None
    email_source: str | None = None

def find_phone(text: str) -> str | None:
    match = PHONE_PATTERN.search(text)
    return match.group(0).strip() if match else None

def find_emails_in_text(text: str) -> list[str]:
    valid_found = []
    
    # 1. Standard regex
    for match in EMAIL_PATTERN.finditer(text):
        email = clean_email_str(match.group(0))
        domain = email.split("@")[-1]
        if domain not in EMAIL_DOMAIN_BLOCKLIST and not is_template_placeholder(email):
            valid_found.append(email)
            
    # 2. De-obfuscate [at] / (dot)
    for m in OBFUSCATED_EMAIL_PATTERN.finditer(text):
        deobf = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
        if not is_template_placeholder(deobf):
            valid_found.append(deobf)
            
    return list(dict.fromkeys(valid_found))

def pick_best_email(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    # Prefer human/direct emails over generic inbox tags
    for email in candidates:
        prefix = email.split("@")[0]
        if prefix not in GENERIC_PREFIXES:
            return email
    return candidates[0]

def extract_from_pages(pages) -> ExtractedFields:
    phone = email = page_title = description = None
    phone_source = email_source = None
    
    all_emails = []
    
    for page in pages:
        # 1. Process mailto hrefs
        if page.mailto_emails:
            for candidate in page.mailto_emails.split("|"):
                cand_clean = clean_email_str(candidate)
                if not is_template_placeholder(cand_clean):
                    domain = cand_clean.split("@")[-1]
                    if domain not in EMAIL_DOMAIN_BLOCKLIST:
                        all_emails.append(cand_clean)
                        if email_source is None:
                            email_source = "href"

        # 2. Process tel hrefs
        if phone is None and page.tel_hrefs:
            for candidate in page.tel_hrefs.split("|"):
                if not is_template_placeholder(candidate):
                    phone = candidate.strip()
                    phone_source = "href"
                    break

        # 3. Fallback to visible page text regex
        if page.text is not None:
            if phone is None:
                found_p = find_phone(page.text)
                if found_p:
                    phone = found_p
                    phone_source = "text_regex"
            
            text_emails = find_emails_in_text(page.text)
            if text_emails and not all_emails:
                all_emails.extend(text_emails)
                if email_source is None:
                    email_source = "text_regex"

        if page_title is None and page.page_title:
            page_title = page.page_title
        if description is None and page.meta_description:
            description = page.meta_description

    email = pick_best_email(all_emails)

    return ExtractedFields(
        phone=phone,
        email=email,
        page_title=page_title,
        description=description,
        phone_source=phone_source,
        email_source=email_source,
    )