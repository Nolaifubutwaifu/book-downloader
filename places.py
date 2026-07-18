"""
places.py - find businesses via the Google Places API (New).

Given a category + area (e.g. "cafe" in "Saint Lucia, Brisbane"), return a list
of businesses with their website URLs, so their sites can be scraped for emails.
Google Places does NOT expose email addresses - only name / website / phone /
address - so the website is what makes the rest of the pipeline work.

Needs a Google Maps Platform API key with the Places API (New) enabled and
billing turned on. Put the key in places_api_key.txt (gitignored) or set the
GOOGLE_MAPS_API_KEY environment variable.
"""

import os
import time
from pathlib import Path

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
KEY_FILE = "places_api_key.txt"
FIELD_MASK = ",".join([
    "places.displayName",
    "places.websiteUri",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "nextPageToken",
])
MAX_CAP = 60


def load_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if key:
        return key
    if Path(KEY_FILE).exists():
        key = Path(KEY_FILE).read_text(encoding="utf-8").strip()
        if key:
            return key
    raise RuntimeError(
        "No Google Places API key found. Put your key in places_api_key.txt "
        "or set GOOGLE_MAPS_API_KEY. (See README - Find businesses with Google Places.)"
    )


def search_businesses(category, area, max_results=20):
    """Return [{business_name, url, address, phone}] for the query."""
    category = (category or "").strip()
    area = (area or "").strip()
    if not category and not area:
        return []
    query = f"{category} in {area}".strip() if area else category
    max_results = max(1, min(int(max_results or 20), MAX_CAP))

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": load_api_key(),
        "X-Goog-FieldMask": FIELD_MASK,
    }

    out = []
    page_token = None
    first = True
    while len(out) < max_results:
        body = {"textQuery": query, "pageSize": min(20, max_results - len(out))}
        if page_token:
            body["pageToken"] = page_token
        r = requests.post(SEARCH_URL, headers=headers, json=body, timeout=20)
        if not r.ok:
            if first:
                try:
                    msg = r.json().get("error", {}).get("message", r.text)
                except Exception:
                    msg = r.text
                raise RuntimeError(f"Places API error ({r.status_code}): {msg}")
            break  # a later page failed - just return what we already have
        data = r.json()
        for p in data.get("places", []):
            out.append({
                "business_name": (p.get("displayName") or {}).get("text", ""),
                "url": p.get("websiteUri", ""),
                "address": p.get("formattedAddress", ""),
                "phone": p.get("nationalPhoneNumber", ""),
            })
        first = False
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)  # the next-page token needs a moment to become valid
    return out[:max_results]
