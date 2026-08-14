"""
HOOD entry point - extraction stage.

Run this AFTER run_crawl.py has populated `pages` for some businesses
(status='crawled').

For every crawled business:
  1. load its saved pages
  2. pull phone / email / page title / meta description
  3. upsert the result into `extracted_data`

Safe to re-run - extraction overwrites the previous result for each
business rather than creating duplicate rows.
"""

from dotenv import load_dotenv

from core.db import get_engine, get_crawled_businesses, get_pages_for_business, upsert_extracted_data
from core.extractor import extract_from_pages


def main():
    load_dotenv()
    engine = get_engine()

    crawled = get_crawled_businesses(engine)
    print(f"{len(crawled)} crawled businesses to extract from")

    found_phone = found_email = found_title = found_description = 0

    for business in crawled:
        pages = get_pages_for_business(engine, business.id)
        fields = extract_from_pages(pages)

        upsert_extracted_data(
            engine, business.id, fields.phone, fields.email, fields.page_title, fields.description,
            fields.phone_source, fields.email_source,
        )

        found_phone += fields.phone is not None
        found_email += fields.email is not None
        found_title += fields.page_title is not None
        found_description += fields.description is not None

        print(f"  {business.canonical_domain}: phone={fields.phone!r} email={fields.email!r}")

    print()
    print("Extraction run complete.")
    print(f"  Businesses processed: {len(crawled)}")
    print(f"  Phone found:          {found_phone}")
    print(f"  Email found:          {found_email}")
    print(f"  Page title found:     {found_title}")
    print(f"  Description found:    {found_description}")


if __name__ == "__main__":
    main()
