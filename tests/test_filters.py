"""Tiered keyword matcher tests."""

from __future__ import annotations

from tenderwatch.filters import KeywordMatcher

PRODUCT = ["bitumen", "emulsion", "crmb", "pmb", "asphalt", "pothole", "vg30"]
ROAD = ["road", "highway", "bridge", "cc road", "rob", "सड़क"]


def matcher(**kwargs) -> KeywordMatcher:
    return KeywordMatcher(PRODUCT, ROAD, kwargs.get("exclude", []), kwargs.get("org", False))


def test_product_tier_wins() -> None:
    m = matcher()
    assert m.tier("Supply of CRMB for NH-44 widening") == "product"
    assert m.tier("Procurement of bitumen emulsion SS2") == "product"
    assert m.tier("Construction of CC road in ward 7") == "road"
    assert m.tier("Supply of office furniture") is None


def test_product_beats_road_when_both_present() -> None:
    m = matcher()
    # contains both "road" (road) and "bitumen" (product) -> product wins
    assert m.tier("Bitumen resurfacing of village road") == "product"


def test_word_boundaries() -> None:
    m = matcher()
    assert m.tier("Construction of ROB at km 12") == "road"
    assert m.tier("Payment to Robert Associates") is None
    assert m.tier("Wardrobe supply for hostel") is None


def test_hindi_substring() -> None:
    m = matcher()
    assert m.tier("ग्राम पंचायत में सड़क निर्माण") == "road"


def test_exclude_veto() -> None:
    m = matcher(exclude=["streetlight"])
    assert m.tier("Streetlight installation along road") is None
    assert m.tier("Widening of road near bridge") == "road"


def test_matches_helper() -> None:
    m = matcher()
    assert m.matches("CC road work") is True
    assert m.matches("Supply of computers") is False


def test_organisation_matching_flag() -> None:
    title_only = KeywordMatcher(PRODUCT, ["road"], [], match_organisation=False)
    with_org = KeywordMatcher(PRODUCT, ["road"], [], match_organisation=True)
    assert title_only.tier("Beat 126", "Road Construction Dept") is None
    assert with_org.tier("Beat 126", "Road Construction Dept") == "road"
