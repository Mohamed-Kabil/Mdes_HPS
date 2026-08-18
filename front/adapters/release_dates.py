"""
release_dates.py — turns the free-text dates found in MDES release notes
("8 July 2026", "2 Jan 2025", ...) into sortable/filterable ISO dates, shared
by predig_adapter.py and mdescs_adapter.py so the releases timeline can sort
and date-range-filter both networks the same way.
"""

from dateutil import parser as _date_parser


def parse_release_date(value):
    """Best-effort parse of a release-note date string to a date() object,
    or None if it can't be parsed (kept out of date-sort/filtering rather
    than guessed)."""
    if not value:
        return None
    try:
        return _date_parser.parse(value, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def display_url(url):
    """Note URLs are fetched via the '/index.md' trick (any developer.
    mastercard.com page returns clean Markdown at that suffix) -- strip it
    back off for display links so they open the real human-readable release
    page instead of the raw Markdown response."""
    if url and url.endswith("/index.md"):
        return url[: -len("index.md")]
    return url


def best_date_iso(*candidates):
    """First candidate (in priority order) that parses to a real date,
    as an ISO string for sorting/filtering; None if none parse."""
    for value in candidates:
        parsed = parse_release_date(value)
        if parsed:
            return parsed.isoformat()
    return None
