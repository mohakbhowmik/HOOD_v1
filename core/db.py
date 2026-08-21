"""
Database layer. All SQL / schema lives here - no other file should know
what the tables look like.

We use SQLAlchemy Core (not the ORM). This means we work with plain
Python data (dicts, rows) instead of model classes with hidden behaviour -
easier to read when you're still learning, and easier to reason about
exactly what SQL is being run.
"""

import os
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    TIMESTAMP,
    ForeignKey,
    UniqueConstraint,
    func,
    select,
    insert,
    update,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

metadata = MetaData()

# One row per real-world business, deduplicated by domain.
# This is the "identity" table - everything else points back to it.
businesses = Table(
    "businesses",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("canonical_domain", String, nullable=False, unique=True),
    Column("name", String, nullable=True),
    Column("status", String, nullable=False, server_default="pending"),
    # pending | crawling | crawled | failed_retryable | failed_permanent | skipped
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_attempted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

# One row per (source, query) that surfaced a business. A single business
# can have many candidate rows if multiple queries/sources found it - that's
# intentional, it's discovery history, not the deduplicated identity.
candidates = Table(
    "candidates",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False),
    Column("source", String, nullable=False),
    Column("query", String, nullable=False),
    Column("raw_url", String, nullable=True),
    Column("run_id", String, nullable=False),
    Column("discovered_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

# One row per successful crawl of a business's homepage.
# Current extracted state per business - NOT a log. Re-running extraction
# overwrites the row for that business (unique constraint below). Unlike
# `pages`/`candidates`, there's no value in keeping stale versions of a
# phone number around.
extracted_data = Table(
    "extracted_data",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False, unique=True),
    Column("phone", String, nullable=True),
    Column("public_email", String, nullable=True),
    Column("phone_source", String, nullable=True),   # 'href' | 'text_regex'
    Column("email_source", String, nullable=True),   # 'href' | 'text_regex'
    Column("page_title", String, nullable=True),
    Column("description", Text, nullable=True),
    Column("extracted_at", TIMESTAMP(timezone=True), server_default=func.now()),
)


# One row per page we successfully OR unsuccessfully attempted to fetch.
# Rows with error IS NOT NULL are failed fetch attempts - kept for
# debugging ("why did we think this business had no site?").
pages = Table(
    "pages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False),
    Column("url", String, nullable=False),
    Column("status_code", Integer, nullable=True),
    Column("text", Text, nullable=True),
    Column("page_title", String, nullable=True),
    Column("meta_description", Text, nullable=True),
    Column("mailto_emails", Text, nullable=True),  # pipe-separated
    Column("tel_hrefs", Text, nullable=True),        # pipe-separated
    Column("error", Text, nullable=True),
    Column("fetched_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

# One row per discovery run. Lets n8n know which industry/location/date
# a business came from, for naming sheets and for scoring context.
runs = Table(
    "runs",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("industry", String, nullable=False),
    Column("locations", String, nullable=False),  # comma-joined, e.g. "Miami"
    Column("target_limit", Integer, nullable=True),
    Column("started_at", TIMESTAMP(timezone=True), server_default=func.now()),
)

# Tracks whether a business has been scored and exported to a sheet yet.
# This is what makes the n8n workflow safe to run repeatedly - once a
# business has a row here, prospects_for_scoring (a SQL view, created
# separately - see init_db) stops returning it, so no duplicate scoring
# or outreach.
outreach_state = Table(
    "outreach_state",
    metadata,
    Column("business_id", Integer, ForeignKey("businesses.id"), primary_key=True),
    Column("fit_score", Integer, nullable=True),
    Column("score_reasoning", Text, nullable=True),
    Column("scored_at", TIMESTAMP(timezone=True), nullable=True),
    Column("sheet_name", String, nullable=True),
    Column("exported_at", TIMESTAMP(timezone=True), nullable=True),
)


def get_engine():
    """
    Creates a SQLAlchemy engine from the DATABASE_URL environment variable.
    Call this once per process and reuse the engine - don't create a new
    one per function call.

    A blank or missing DATABASE_URL should not crash the local pipeline.
    We intentionally fall back to the project Docker database so n8n can
    run without depending on a working .env parser while we're validating
    the end-to-end flow.
    """
    database_url = os.getenv("DATABASE_URL") or "postgresql+psycopg2://hood:changeme@localhost:5432/hood"
    return create_engine(database_url)


def init_db(engine) -> None:
    """
    Creates all tables if they don't already exist, plus the
    prospects_for_scoring view n8n reads from. Safe to call every time
    the app starts.
    """
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW prospects_for_scoring AS
            SELECT
                b.id AS business_id,
                b.canonical_domain,
                b.name AS business_name,
                ed.phone,
                ed.public_email,
                ed.phone_source,
                ed.email_source,
                ed.page_title,
                ed.description,
                r.run_id,
                r.industry,
                r.locations,
                r.started_at AS run_started_at
            FROM businesses b
            JOIN extracted_data ed ON ed.business_id = b.id
            JOIN LATERAL (
                SELECT c.run_id
                FROM candidates c
                WHERE c.business_id = b.id
                ORDER BY c.discovered_at ASC
                LIMIT 1
            ) first_candidate ON true
            JOIN runs r ON r.run_id = first_candidate.run_id
            LEFT JOIN outreach_state os ON os.business_id = b.id
            WHERE b.status = 'crawled'
              AND os.business_id IS NULL
        """))


def create_run(engine, run_id: str, industry: str, locations: list[str], target_limit: int) -> None:
    """Records metadata for a discovery run - what n8n uses to name sheets."""
    with engine.begin() as conn:
        conn.execute(
            insert(runs).values(
                run_id=run_id,
                industry=industry,
                locations=", ".join(locations),
                target_limit=target_limit,
            )
        )


def upsert_business(engine, domain: str, name: str | None) -> int:
    """
    Returns the business id for this domain. If we've seen this domain
    before, returns the existing row's id untouched (this is our dedup
    point). If not, inserts a new row with status='pending' and returns
    its new id.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(businesses.c.id).where(businesses.c.canonical_domain == domain)
        ).first()
        if existing is not None:
            return existing.id

        result = conn.execute(
            insert(businesses).values(canonical_domain=domain, name=name)
        )
        return result.inserted_primary_key[0]


def insert_candidate(
    engine, business_id: int, source: str, query: str, raw_url: str | None, run_id: str
) -> None:
    """
    Records that a given (source, query) surfaced this business. This is
    discovery history - we insert one of these every time, even if the
    business already existed (that's a legitimate second confirmation,
    not something to deduplicate away).
    """
    with engine.begin() as conn:
        conn.execute(
            insert(candidates).values(
                business_id=business_id,
                source=source,
                query=query,
                raw_url=raw_url,
                run_id=run_id,
            )
        )


def get_pending_businesses(engine, limit: int | None = None):
    """Returns rows (id, canonical_domain, name) for businesses awaiting crawl."""
    with engine.begin() as conn:
        query = select(
            businesses.c.id, businesses.c.canonical_domain, businesses.c.name
        ).where(businesses.c.status == "pending")
        if limit is not None:
            query = query.limit(limit)
        return conn.execute(query).fetchall()


def save_pages(engine, business_id: int, page_results) -> None:
    """Saves every fetched page (successful or failed) for a business."""
    with engine.begin() as conn:
        for page in page_results:
            conn.execute(
                insert(pages).values(
                    business_id=business_id,
                    url=page.url,
                    status_code=page.status_code,
                    text=page.text,
                    page_title=page.page_title,
                    meta_description=page.meta_description,
                    mailto_emails="|".join(page.mailto_emails) or None,
                    tel_hrefs="|".join(page.tel_hrefs) or None,
                    error=page.error,
                )
            )


def mark_business_crawled(engine, business_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(businesses)
            .where(businesses.c.id == business_id)
            .values(status="crawled", last_attempted_at=func.now())
        )


def mark_business_failed(engine, business_id: int, status: str, error: str) -> None:
    """status should be 'failed_retryable' or 'failed_permanent'."""
    with engine.begin() as conn:
        conn.execute(
            update(businesses)
            .where(businesses.c.id == business_id)
            .values(
                status=status,
                attempts=businesses.c.attempts + 1,
                last_attempted_at=func.now(),
                last_error=error,
            )
        )


def get_crawled_businesses(engine):
    """Returns rows (id, canonical_domain, name) for businesses ready to extract from."""
    with engine.begin() as conn:
        query = select(
            businesses.c.id, businesses.c.canonical_domain, businesses.c.name
        ).where(businesses.c.status == "crawled")
        return conn.execute(query).fetchall()


def get_pages_for_business(engine, business_id: int):
    """
    Returns saved pages for a business, homepage first. Ordering by id
    works because save_pages() inserts them in fetch order (homepage,
    then followed links) and each business is only crawled once in V1.
    """
    with engine.begin() as conn:
        query = (
            select(
                pages.c.text, pages.c.page_title, pages.c.meta_description,
                pages.c.mailto_emails, pages.c.tel_hrefs,
            )
            .where(pages.c.business_id == business_id)
            .order_by(pages.c.id.asc())
        )
        return conn.execute(query).fetchall()


def upsert_extracted_data(
    engine, business_id: int, phone: str | None, email: str | None,
    page_title: str | None, description: str | None,
    phone_source: str | None = None, email_source: str | None = None,
) -> None:
    """Insert or overwrite the extracted fields for this business."""
    stmt = pg_insert(extracted_data).values(
        business_id=business_id,
        phone=phone,
        public_email=email,
        phone_source=phone_source,
        email_source=email_source,
        page_title=page_title,
        description=description,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[extracted_data.c.business_id],
        set_={
            "phone": stmt.excluded.phone,
            "public_email": stmt.excluded.public_email,
            "phone_source": stmt.excluded.phone_source,
            "email_source": stmt.excluded.email_source,
            "page_title": stmt.excluded.page_title,
            "description": stmt.excluded.description,
            "extracted_at": func.now(),
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
