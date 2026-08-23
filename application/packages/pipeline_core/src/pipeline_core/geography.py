"""Geographic ranking of trial sites: Ireland first, then rest of Europe, then US.

Uses a small static country-centroid table (no network/geocoding dependency)
and haversine distance for secondary ordering within each tier.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

IRELAND = (53.4129, -8.2439)

# Approximate country centroids (lat, lon). Extend as needed; unknown
# countries fall back to a neutral (None) tier ordered last.
COUNTRY_COORDINATES: dict[str, tuple[float, float]] = {
    "ireland": (53.4129, -8.2439),
    "united kingdom": (55.3781, -3.4360),
    "france": (46.2276, 2.2137),
    "germany": (51.1657, 10.4515),
    "spain": (40.4637, -3.7492),
    "italy": (41.8719, 12.5674),
    "netherlands": (52.1326, 5.2913),
    "belgium": (50.5039, 4.4699),
    "switzerland": (46.8182, 8.2275),
    "austria": (47.5162, 14.5501),
    "portugal": (39.3999, -8.2245),
    "sweden": (60.1282, 18.6435),
    "denmark": (56.2639, 9.5018),
    "norway": (60.4720, 8.4689),
    "finland": (61.9241, 25.7482),
    "poland": (51.9194, 19.1451),
    "united states": (39.8283, -98.5795),
}

EUROPE = {
    "ireland",
    "united kingdom",
    "france",
    "germany",
    "spain",
    "italy",
    "netherlands",
    "belgium",
    "switzerland",
    "austria",
    "portugal",
    "sweden",
    "denmark",
    "norway",
    "finland",
    "poland",
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


@dataclass
class RankedSite:
    country: str
    tier: int  # 0 = Ireland, 1 = rest of Europe, 2 = US, 3 = unranked/other
    distance_from_ireland_km: float | None
    included: bool


def rank_site(country: str | None) -> RankedSite:
    """Classify and rank a single trial site. ``included`` is False for
    countries outside the Europe/US scope the plan restricts trials to."""
    normalized = (country or "").strip().lower()
    coords = COUNTRY_COORDINATES.get(normalized)

    if normalized == "ireland":
        tier = 0
    elif normalized in EUROPE:
        tier = 1
    elif normalized == "united states":
        tier = 2
    else:
        return RankedSite(country=country or "unknown", tier=3, distance_from_ireland_km=None, included=False)

    distance = haversine_km(IRELAND, coords) if coords else None
    return RankedSite(country=country, tier=tier, distance_from_ireland_km=distance, included=True)


def rank_sites(countries: list[str]) -> list[RankedSite]:
    ranked = [rank_site(c) for c in countries]
    ranked.sort(
        key=lambda site: (
            site.tier,
            site.distance_from_ireland_km if site.distance_from_ireland_km is not None else math.inf,
        )
    )
    return ranked
