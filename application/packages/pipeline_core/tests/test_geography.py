from pipeline_core.geography import haversine_km, rank_site, rank_sites


def test_ireland_is_tier_zero_with_zero_distance():
    site = rank_site("Ireland")
    assert site.tier == 0
    assert site.distance_from_ireland_km == 0 or site.distance_from_ireland_km < 1


def test_rest_of_europe_ranked_before_us():
    us = rank_site("United States")
    uk = rank_site("United Kingdom")
    assert uk.tier < us.tier


def test_unknown_country_excluded():
    site = rank_site("Brazil")
    assert site.included is False
    assert site.tier == 3


def test_rank_sites_orders_ireland_first_then_europe_then_us():
    ranked = rank_sites(["United States", "France", "Ireland", "Germany"])
    countries_in_order = [s.country for s in ranked]
    assert countries_in_order[0] == "Ireland"
    assert countries_in_order[-1] == "United States"


def test_haversine_symmetric():
    a, b = (53.0, -8.0), (48.8, 2.3)
    assert abs(haversine_km(a, b) - haversine_km(b, a)) < 1e-9
