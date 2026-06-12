"""Keyword matching and relevance tiering for tenders.

Two tiers reflect how directly a tender maps to HINCOL's business:

* ``product`` - the tender names a HINCOL product or bituminous binder
  (bitumen emulsion, CRMB/PMB, microsurfacing, VG grades, ...). HINCOL's
  materials are explicitly specified, so these are the highest-value leads.
* ``road`` - general road/pavement work where a bituminous binder is
  likely required even if not named.

Product is checked first and wins when both match.
"""

from __future__ import annotations

import re

PRODUCT_TIER = "product"
ROAD_TIER = "road"


class KeywordMatcher:
    """Tiered word-boundary keyword matcher with an exclude veto.

    ASCII keywords are matched on word boundaries (so ``rob`` matches
    "ROB" but not "Robert"); non-ASCII keywords (Devanagari) are matched
    as plain substrings.

    Parameters
    ----------
    product_keywords : list of str
        Tier 1 keywords (HINCOL products / binders).
    road_keywords : list of str
        Tier 2 keywords (general road work).
    exclude_keywords : list of str
        Keywords that veto a match in either tier.
    match_organisation : bool
        When True, the organisation chain is searched in addition to the
        title.
    """

    def __init__(
        self,
        product_keywords: list[str],
        road_keywords: list[str],
        exclude_keywords: list[str] | None = None,
        match_organisation: bool = False,
    ) -> None:
        self.product_re = self._compile(product_keywords)
        self.road_re = self._compile(road_keywords)
        self.exclude_re = self._compile(exclude_keywords or [])
        self.match_organisation = match_organisation

    @staticmethod
    def _compile(keywords: list[str]) -> re.Pattern | None:
        if not keywords:
            return None
        parts = []
        for keyword in keywords:
            cleaned = keyword.strip()
            if not cleaned:
                continue
            escaped = re.escape(cleaned).replace(r"\ ", r"\s+")
            if cleaned.isascii():
                parts.append(rf"\b{escaped}\b")
            else:
                parts.append(escaped)
        if not parts:
            return None
        return re.compile("|".join(parts), re.IGNORECASE)

    def tier(self, title: str, organisation: str = "") -> str | None:
        """Return the relevance tier for a tender, or None if irrelevant.

        Parameters
        ----------
        title : str
            Tender title text.
        organisation : str
            Organisation chain text (only used when configured).

        Returns
        -------
        str or None
            ``"product"``, ``"road"``, or None.

        Example
        -------
        >>> matcher.tier("Supply of CRMB for NH widening")
        'product'
        >>> matcher.tier("Construction of CC road in ward 7")
        'road'
        """
        haystack = title
        if self.match_organisation and organisation:
            haystack = f"{title} || {organisation}"
        if self.exclude_re is not None and self.exclude_re.search(haystack):
            return None
        if self.product_re is not None and self.product_re.search(haystack):
            return PRODUCT_TIER
        if self.road_re is not None and self.road_re.search(haystack):
            return ROAD_TIER
        return None

    def matches(self, title: str, organisation: str = "") -> bool:
        """Return True when the tender is relevant in either tier."""
        return self.tier(title, organisation) is not None
