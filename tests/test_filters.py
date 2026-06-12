"""Keyword matcher tests."""

from __future__ import annotations

from tenderwatch.filters import KeywordMatcher

KEYWORDS = ["road", "highway", "bridge", "cc road", "rob", "सड़क"]


def test_basic_match() -> None:
    matcher = KeywordMatcher(KEYWORDS)
    assert matcher.matches("Construction of CC Road at Ward 7")
    assert matcher.matches("Four laning of national HIGHWAY section")
    assert not matcher.matches("Supply of office furniture")


def test_word_boundaries() -> None:
    matcher = KeywordMatcher(KEYWORDS)
    assert matcher.matches("Construction of ROB at km 12")
    assert not matcher.matches("Payment to Robert Associates")
    assert not matcher.matches("Wardrobe supply for hostel")


def test_hindi_substring() -> None:
    matcher = KeywordMatcher(KEYWORDS)
    assert matcher.matches("ग्राम पंचायत में सड़क निर्माण कार्य")


def test_exclude_veto() -> None:
    matcher = KeywordMatcher(KEYWORDS, exclude=["streetlight"])
    assert not matcher.matches("Streetlight installation along road")
    assert matcher.matches("Widening of road near bridge")


def test_organisation_matching_flag() -> None:
    title_only = KeywordMatcher(["road"], match_organisation=False)
    with_org = KeywordMatcher(["road"], match_organisation=True)
    assert not title_only.matches("Beat 126", "Road Construction Department")
    assert with_org.matches("Beat 126", "Road Construction Department")
