"""
HOOD entry point - full pipeline, one call per (industry, city) submission.

This is the file n8n's Execute Command node runs. n8n's flow is:
  1. person enters industry + city in n8n
  2. n8n's AI node expands that into a wide range of specific search
     phrases (sub-niches, neighborhoods, service variations)
  3. n8n runs this script, passing industry/city/limit/that query list
  4. this script runs discovery -> crawl -> extract, in order, and exits

Usage (called by n8n, with AI-generated keywords):
  python run_pipeline.py --industry "real estate" --locations "Miami" \\
      --limit 50 \\
      --queries "luxury condo agents Brickell|vacation rental management Coral Gables|..."

Usage (manual, no AI expansion - falls back to basic template queries):
  python run_pipeline.py --industry "real estate" --locations "Miami" --limit 50

--locations accepts a comma-separated list if you ever want multiple
cities in one run, but the intended n8n flow is one city per submission.
--queries is pipe-separated ("|") since search phrases can contain commas.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from dotenv import load_dotenv

from core.config import Target
from core.crawler import crawl_business
from core.db import (
    create_run,
    get_crawled_businesses,
    get_engine,
    init_db,
    insert_candidate,
    mark_business_crawled,
    mark_business_failed,
    save_pages,
    upsert_business,
    upsert_extracted_data,
)
from core.discovery import discover, generate_queries
from core.extractor import extract_from_pages
from core.urls import canonical_domain


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full HOOD pipeline for one target")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--locations", required=True,
                         help="comma-separated, e.g. 'Miami' or 'Miami,Fort Lauderdale'")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--queries", default=None,
                         help="pipe-separated search phrases, e.g. from n8n's AI keyword expansion")
    return parser.parse_args()


def normalize_pages_for_extractor(page_results):
    """Convert crawler PageResult objects to the shape expected by the existing extractor."""
    normalized = []
    for page in page_results:
        normalized.append(SimpleNamespace(
            text=page.text,
            page_title=page.page_title,
            meta_description=page.meta_description,
            mailto_emails="|".join(page.mailto_emails) if page.mailto_emails else None,
            tel_hrefs="|".join(page.tel_hrefs) if page.tel_hrefs else None,
        ))
    return normalized


async def run_pipeline_async(engine, target: Target, run_id: str) -> None:
    discovery_to_crawler_queue: asyncio.Queue = asyncio.Queue()
    crawler_to_extractor_queue: asyncio.Queue = asyncio.Queue()
    stop_event = asyncio.Event()
    extracted_leads_count = 0
    count_lock = asyncio.Lock()
    discovery_done = False

    print("\n=== Discovery ===")
    queries = generate_queries(target)
    print(f"Generated {len(queries)} queries for run_id={run_id}")

    async def producer_task():
        nonlocal discovery_done
        seen_domains = set()
        for query in queries:
            if stop_event.is_set():
                break
            print(f"  searching: {query!r}")
            try:
                raw_candidates = await asyncio.to_thread(discover, query)
            except Exception as exc:
                print(f"    discovery error: {exc}")
                continue

            for candidate in raw_candidates:
                if stop_event.is_set():
                    break
                domain = canonical_domain(candidate.url)
                if domain is None or domain in seen_domains:
                    continue
                seen_domains.add(domain)

                business_id = upsert_business(engine, domain, candidate.name)
                insert_candidate(engine, business_id, candidate.source, candidate.query, candidate.url, run_id)
                print(f"    discovered: {domain}")
                await discovery_to_crawler_queue.put((business_id, domain))

        discovery_done = True

    async def crawler_worker():
        while not stop_event.is_set():
            try:
                item = discovery_to_crawler_queue.get_nowait()
            except asyncio.QueueEmpty:
                if discovery_done:
                    return
                await asyncio.sleep(0.1)
                continue

            business_id, domain = item
            try:
                print(f"  crawling: {domain}")
                pages_fetched = await asyncio.to_thread(crawl_business, domain)
                save_pages(engine, business_id, pages_fetched)

                homepage_result = pages_fetched[0]
                if homepage_result.error is None:
                    mark_business_crawled(engine, business_id)
                    print(f"    ok - {len(pages_fetched)} page(s) fetched")
                    await crawler_to_extractor_queue.put((business_id, domain, normalize_pages_for_extractor(pages_fetched)))
                else:
                    status = (
                        "failed_retryable" if homepage_result.failure_type == "transient"
                        else "failed_permanent"
                    )
                    mark_business_failed(engine, business_id, status, homepage_result.error)
                    print(f"    failed ({status}): {homepage_result.error}")
            except Exception as exc:
                print(f"    crawl error for {domain}: {exc}")
            finally:
                discovery_to_crawler_queue.task_done()

    async def extractor_worker():
        nonlocal extracted_leads_count
        while not stop_event.is_set():
            try:
                item = crawler_to_extractor_queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
                continue

            business_id, domain, pages = item
            try:
                fields = await asyncio.to_thread(extract_from_pages, pages)
                upsert_extracted_data(
                    engine,
                    business_id,
                    fields.phone,
                    fields.email,
                    fields.page_title,
                    fields.description,
                    fields.phone_source,
                    fields.email_source,
                )

                async with count_lock:
                    extracted_leads_count += 1
                    print(f"  extracted: {domain} -> phone={fields.phone!r} email={fields.email!r}")
                    if extracted_leads_count >= target.limit:
                        stop_event.set()
                        print(f"\nEarly exit triggered at limit={target.limit}")
            except Exception as exc:
                print(f"    extraction error for {domain}: {exc}")
            finally:
                crawler_to_extractor_queue.task_done()

    create_run(engine, run_id, target.industry, target.locations, target.limit)

    producer = asyncio.create_task(producer_task())
    crawler_workers = [asyncio.create_task(crawler_worker()) for _ in range(min(4, max(1, len(queries))))]
    extractor_workers = [asyncio.create_task(extractor_worker()) for _ in range(min(4, max(1, len(queries))))]
    tasks = [producer, *crawler_workers, *extractor_workers]

    try:
        await producer
        while not stop_event.is_set():
            if discovery_done and discovery_to_crawler_queue.empty() and all(task.done() for task in crawler_workers):
                break
            await asyncio.sleep(0.05)

        if stop_event.is_set():
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            while not discovery_to_crawler_queue.empty():
                discovery_to_crawler_queue.get_nowait()
            while not crawler_to_extractor_queue.empty():
                crawler_to_extractor_queue.get_nowait()
    except asyncio.CancelledError:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    print("\n=== Crawl ===")
    print("\n=== Extract ===")

    businesses_crawled = extracted_leads_count
    print(f"\nPipeline complete. run_id={run_id}")
    print("Query `SELECT * FROM prospects_for_scoring;` in Postgres to see results ready for n8n.")
    print(json.dumps({
        "run_id": run_id,
        "industry": target.industry,
        "locations": target.locations,
        "businesses_crawled": businesses_crawled,
        "status": "completed",
    }))


def main():
    args = parse_args()
    load_dotenv()

    locations = [loc.strip() for loc in args.locations.split(",") if loc.strip()]
    queries = [q.strip() for q in args.queries.split("|") if q.strip()] if args.queries else None

    target = Target(industry=args.industry, locations=locations, limit=args.limit, queries=queries)
    print(f"Target: industry={target.industry!r}, locations={target.locations}, "
          f"limit={target.limit}, explicit_queries={len(queries) if queries else 0}")

    engine = get_engine()
    init_db(engine)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    asyncio.run(run_pipeline_async(engine, target, run_id))


if __name__ == "__main__":
    main()
