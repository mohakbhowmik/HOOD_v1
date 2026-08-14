"""
Loads a target definition (industry + locations + limit) from a JSON file.

Kept deliberately minimal for V0 - just the three fields we actually use.
Add fields here only when a real component needs them (e.g. "keywords"
gets added when the query generator actually uses keywords).
"""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class Target:
    industry: str
    locations: list[str]
    limit: int

    @classmethod
    def from_file(cls, path: str | Path) -> "Target":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            industry=data["industry"],
            locations=data["locations"],
            limit=data["limit"],
        )
