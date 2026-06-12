"""Keyword matching for tender relevance flagging."""

from __future__ import annotations

import re


class KeywordMatcher:
    """Word-boundary keyword matcher with include/exclude lists.

    ASCII keywords are matched on word boundaries (so "rob" matches
    "ROB" but not "Robert"); non-ASCII keywords (Hindi) are matched as
    plain substrings.

    Parameters
    ----------
    include : list of str
        Keywords or phrases that flag a tender as relevant.
    exclude : list of str
        Keywords that veto a match even when an include keyword hits.
    match_organisation : bool
        When True, the organisation chain is searched in addition to
        the title.
    """

    def __init__(
        self,
        include: list[str],
        exclude: list[str] | None = None,
        match_organisation: bool = False,
    ) -> None:
        self.include_re = self._compile(include)
        self.exclude_re = self._compile(exclude or [])
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

    def matches(self, title: str, organisation: str = "") -> bool:
        """Return True when the tender should be flagged as relevant.

        Parameters
        ----------
        title : str
            Tender title text.
        organisation : str
            Organisation chain text (only used when configured).

        Returns
        -------
        bool
            True when an include keyword hits and no exclude keyword does.
        """
        haystack = title
        if self.match_organisation and organisation:
            haystack = f"{title} || {organisation}"
        if self.include_re is None or not self.include_re.search(haystack):
            return False
        if self.exclude_re is not None and self.exclude_re.search(haystack):
            return False
        return True
