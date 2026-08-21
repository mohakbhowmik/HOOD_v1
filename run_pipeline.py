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
import json
from datetime import datetime, timezone

from dotenv import load_dotenv

from core.config import Target
from core.db import get_engine, init_db, get_crawled_businesses
from run_discovery import discover_businesses
from run_crawl import crawl_pending_businesses
from run_extract import extract_crawled_businesses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full HOOD pipeline for one target")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--locations", required=True,
                         help="comma-separated, e.g. 'Miami' or 'Miami,Fort Lauderdale'")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--queries", default=None,
                         help="pipe-separated search phrases, e.g. from n8n's AI keyword expansion")
    return parser.parse_args()


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

    print("\n=== Discovery ===")
    discover_businesses(engine, target, run_id)

    print("\n=== Crawl ===")
    crawl_pending_businesses(engine)

    print("\n=== Extract ===")
    extract_crawled_businesses(engine)

    print(f"\nPipeline complete. run_id={run_id}")
    print("Query `SELECT * FROM prospects_for_scoring;` in Postgres to see results ready for n8n.")

    businesses_crawled = len(get_crawled_businesses(engine))

    # Final machine-readable status payload. Keep this as the last line so
    # downstream n8n/automation can parse it without scraping the logs.
    payload = {
        "run_id": run_id,
        "industry": target.industry,
        "locations": target.locations,
        "businesses_crawled": businesses_crawled,
        "status": "completed",
    }
    print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
