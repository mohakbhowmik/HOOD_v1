"""
Query generation + Google Places (New) discovery source.

COST NOTE - read before adding fields:
To get a business's website URL, the Places API requires the field
`websiteUri`, which lives in the ENTERPRISE pricing tier - not Essentials.
Enterprise's free allowance is 1,000 calls/month (Essentials gets 10,000,
Pro gets 5,000). Billing is per SEARCH CALL though (each call can return
up to 20 results), not per result returned - so at our scale (a handful
of queries per target run) we stay well under the free cap.

If you're ever tempted to add `rating`, `nationalPhoneNumber`, or
`regularOpeningHours` to FIELD_MASK: they're already in the Enterprise
tier too, so they're "free" in the sense of not bumping the tier further -
but always re-check the current tier list before adding a field, because
Google can and does move fields between tiers.
"""

import os
from dataclasses import dataclass

import requests

PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri"

# Query templates for V0. Add more strings here to search more phrasings -
# no code change needed elsewhere.
QUERY_TEMPLATES = [
    "{industry} agencies {location}",
    "{industry} brokers {location}",
]


@dataclass
class RawCandidate:
    name: str | None
    url: str | None
    location: str | None
    source: str
    query: str


def generate_queries(target) -> list[str]:
    """Target(industry='real estate', locations=['Miami']) -> list of query strings."""
    queries = []
    for location in target.locations:
        for template in QUERY_TEMPLATES:
            queries.append(template.format(industry=target.industry, location=location))
    return queries


def discover(query: str) -> list[RawCandidate]:
    """Runs one text search query against Google Places and returns raw candidates."""
    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    response = requests.post(
        PLACES_ENDPOINT,
        json={"textQuery": query},
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for place in data.get("places", []):
        results.append(RawCandidate(
            name=place.get("displayName", {}).get("text"),
            url=place.get("websiteUri"),
            location=place.get("formattedAddress"),
            source="google_places",
            query=query,
        ))
    return results
