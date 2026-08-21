"""
HOOD entry point - discovery stage.

Can be run two ways:
  1. Standalone: `python run_discovery.py` - loads targets/miami_real_estate.json,
     uses template query expansion. Useful for manual/local testing.
  2. Imported: run_pipeline.py calls discover_businesses() directly with
     a Target built from n8n-supplied CLI args (industry/locations/queries).

Pipeline:
  1. generate queries from the target (template expansion, or explicit
     target.queries if n8n's AI already supplied them)
  2. run each query against Google Places
  3. normalize each result's URL to a canonical domain
  4. upsert into `businesses` (dedup happens here)
  5. record the discovery in `candidates`
"""

from datetime import datetime, timezone

from dotenv import load_dotenv

from core.config import Target
from core.db import get_engine, init_db, upsert_business, insert_candidate, create_run
from core.discovery import generate_queries, discover
from core.urls import canonical_domain


def discover_businesses(engine, target: Target, run_id: str) -> None:
    """Runs the full discovery stage for one target. Prints a summary."""
    create_run(engine, run_id, target.industry, target.locations, target.limit)
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
    print("Discovery complete.")
    print(f"  Raw candidates returned by Places API: {total_raw}")
    print(f"  Skipped (no usable website URL):       {skipped_no_url}")
    print(f"  Unique businesses (deduped by domain): {len(seen_domains)}")


def main():
    load_dotenv()

    target = Target.from_file("targets/miami_real_estate.json")
    print(f"Loaded target: industry={target.industry!r}, "
          f"locations={target.locations}, limit={target.limit}")

    engine = get_engine()
    init_db(engine)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    discover_businesses(engine, target, run_id)


if __name__ == "__main__":
    main()
