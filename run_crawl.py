"""
HOOD entry point - crawl stage.

Can be run two ways:
  1. Standalone: `python run_crawl.py` - crawls whatever is pending.
  2. Imported: run_pipeline.py calls crawl_pending_businesses() directly
     right after discovery, in the same process/run.

For every pending business:
  1. fetch its homepage (https, falling back to http once if needed)
  2. if that succeeds, follow a small number of relevant internal pages
  3. save every page fetched (success or failure) to `pages`
  4. update the business's status based on the homepage result
"""

import time

from dotenv import load_dotenv

from core.db import (
    get_engine,
    get_pending_businesses,
    save_pages,
    mark_business_crawled,
    mark_business_failed,
)
from core.crawler import crawl_business

DELAY_BETWEEN_BUSINESSES_SECONDS = 1


def crawl_pending_businesses(engine) -> None:
    """Crawls every business with status='pending'. Prints a summary."""
    pending = get_pending_businesses(engine)
    print(f"{len(pending)} businesses pending crawl")

    crawled_ok = 0
    failed_retryable = 0
    failed_permanent = 0

    for business in pending:
        domain = business.canonical_domain
        print(f"  crawling: {domain}")

        pages_fetched = crawl_business(domain)
        save_pages(engine, business.id, pages_fetched)

        homepage_result = pages_fetched[0]
        if homepage_result.error is None:
            mark_business_crawled(engine, business.id)
            crawled_ok += 1
            print(f"    ok - {len(pages_fetched)} page(s) fetched")
        else:
            status = (
                "failed_retryable" if homepage_result.failure_type == "transient"
                else "failed_permanent"
            )
            mark_business_failed(engine, business.id, status, homepage_result.error)
            if status == "failed_retryable":
                failed_retryable += 1
            else:
                failed_permanent += 1
            print(f"    failed ({status}): {homepage_result.error}")

        time.sleep(DELAY_BETWEEN_BUSINESSES_SECONDS)

    print()
    print("Crawl complete.")
    print(f"  Crawled successfully:      {crawled_ok}")
    print(f"  Failed (will retry later): {failed_retryable}")
    print(f"  Failed (permanent):        {failed_permanent}")


def main():
    load_dotenv()
    engine = get_engine()
    crawl_pending_businesses(engine)


if __name__ == "__main__":
    main()
