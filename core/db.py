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
)

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
extracted_data = Table(
    "extracted_data",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False),
    Column("phone", String, nullable=True),
    Column("public_email", String, nullable=True),
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
    Column("error", Text, nullable=True),
    Column("fetched_at", TIMESTAMP(timezone=True), server_default=func.now()),
)


def get_engine():
    """
    Creates a SQLAlchemy engine from the DATABASE_URL environment variable.
    Call this once per process and reuse the engine - don't create a new
    one per function call.
    """
    database_url = os.environ["DATABASE_URL"]
    return create_engine(database_url)


def init_db(engine) -> None:
    """
    Creates all tables if they don't already exist. Safe to call every
    time the app starts - it won't touch tables that already exist.
    """
    metadata.create_all(engine)


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
