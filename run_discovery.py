"""
HOOD entry point - V0.

Pipeline so far:
  1. load target config
  2. connect to Postgres, ensure schema exists
  3. generate queries from the target
  4. run each query against Google Places (our one V0 discovery source)
  5. normalize each result's URL to a canonical domain
  6. upsert into `businesses` (this is where dedup happens)
  7. record the discovery in `candidates`
  8. print a summary

Crawling and extraction are NOT wired in yet - businesses just sit at
status='pending' after this runs. That's next.
"""

from datetime import datetime, timezone

from dotenv import load_dotenv

from core.config import Target
from core.db import get_engine, init_db, upsert_business, insert_candidate
from core.discovery import generate_queries, discover
from core.urls import canonical_domain


def main():
    load_dotenv()

    target = Target.from_file("targets/miami_real_estate.json")
    print(f"Loaded target: industry={target.industry!r}, "
          f"locations={target.locations}, limit={target.limit}")

    engine = get_engine()
    init_db(engine)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    queries = generate_queries(target)
    print(f"Generated {len(queries)} queries for run_id={run_id}")

    total_raw = 0
    skipped_no_url = 0
    seen_domains = set()

    for query in queries:
        print(f"  searching: {query!r}")
        raw_candidates = discover(query)
        total_raw += len(raw_candidates)

        for rc in raw_candidates:
            domain = canonical_domain(rc.url)
            if domain is None:
                skipped_no_url += 1
                continue

            business_id = upsert_business(engine, domain, rc.name)
            insert_candidate(engine, business_id, rc.source, rc.query, rc.url, run_id)
            seen_domains.add(domain)

    print()
    print("Run complete.")
    print(f"  Raw candidates returned by Places API: {total_raw}")
    print(f"  Skipped (no usable website URL):       {skipped_no_url}")
    print(f"  Unique businesses (deduped by domain): {len(seen_domains)}")


if __name__ == "__main__":
    main()
