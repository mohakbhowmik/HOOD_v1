"""
Loads a target definition (industry + locations + limit + optional
explicit queries) from a JSON file, or lets one be built directly from
CLI args (see run_pipeline.py).

`queries`, if provided, is used as-is instead of Python's own template
expansion in core/discovery.py - this is how n8n's AI-generated keyword
list reaches the crawler.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class Target:
    industry: str
    locations: list[str]
    limit: int
    queries: list[str] | None = None  # if set, skip template generation entirely

    @classmethod
    def from_file(cls, path: str | Path) -> "Target":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            industry=data["industry"],
            locations=data["locations"],
            limit=data["limit"],
            queries=data.get("queries"),  # optional - manual target files rarely set this
        )
