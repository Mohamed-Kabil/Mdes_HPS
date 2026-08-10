#!/usr/bin/env python3
"""
fetch_mc_source.py — retrieves and caches Mastercard's two public sources for
the MDES Pre-Digitization divergence pipeline:

  1. The current OpenAPI spec (pre-dig.yaml), fetched directly (no auth
     needed) and cached locally with a timestamp so downstream scripts never
     hit the network themselves.
  2. The release-notes table, fetched via the '/index.md' trick (appending
     index.md to any developer.mastercard.com page returns clean Markdown,
     no HTML scraping needed) and parsed into a JSON list of
     {title, url, mdes_release, note_type, upgrade_date}.

Both caches are consumed by parse_release_note.py / phase1_historical_audit.py
/ phase2_job_a_new_release_alert.py — none of those scripts touch the network
directly, which keeps them testable offline against the cache.

Usage:
    python3 fetch_mc_source.py                  # refresh both caches
    python3 fetch_mc_source.py --spec-only
    python3 fetch_mc_source.py --releases-only
    python3 fetch_mc_source.py --cache-dir cache
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

PRE_DIG_SPEC_URL = "https://static.developer.mastercard.com/content/mdes-pre-digitization/swagger/pre-dig.yaml"
RELEASE_NOTES_INDEX_URL = "https://developer.mastercard.com/mdes-pre-digitization/documentation/pre-release-notes/index.md"

USER_AGENT = "Mozilla/5.0 (compatible; mc-divergence-bot/1.0)"

DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# ============================================================================
# 1. pre-dig.yaml
# ============================================================================

def fetch_pre_dig_spec(cache_dir):
    """Downloads pre-dig.yaml and writes it plus a sidecar
    'pre-dig.yaml.meta.json' recording when it was fetched (so staleness is
    always inspectable without re-fetching)."""
    text = _fetch(PRE_DIG_SPEC_URL)
    spec_path = os.path.join(cache_dir, "pre-dig.yaml")
    meta_path = os.path.join(cache_dir, "pre-dig.yaml.meta.json")

    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "source_url": PRE_DIG_SPEC_URL,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": len(text.encode("utf-8")),
        }, f, indent=2)

    print(f"  [fetch] pre-dig.yaml -> {spec_path} ({len(text)} chars)", file=sys.stderr)
    return spec_path


# ============================================================================
# 2. Release notes table
# ============================================================================

# One markdown table row, e.g.:
# | [November 2026 Pre-Release Notes](https://.../index.md) | 2026 November | Pre-warning Notice | 22 May 2026 |
TABLE_ROW_RE = re.compile(
    r'^\|\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)\s*\|\s*(?P<mdes_release>[^|]+?)\s*\|'
    r'\s*(?P<note_type>[^|]+?)\s*\|\s*(?P<upgrade_date>[^|]+?)\s*\|\s*$'
)


def parse_release_notes_table(markdown_text):
    """Parses the '| [Title](url) | MDES Release | Type | Date |' table into
    a list of dicts, oldest-agnostic (keeps source order, newest-first as
    published by Mastercard)."""
    entries = []
    for line in markdown_text.splitlines():
        m = TABLE_ROW_RE.match(line.strip())
        if not m:
            continue
        entries.append({
            "title": m.group("title").strip(),
            "url": m.group("url").strip(),
            "mdes_release": m.group("mdes_release").strip(),
            "note_type": m.group("note_type").strip(),
            "upgrade_date": m.group("upgrade_date").strip(),
        })
    return entries


def fetch_release_notes(cache_dir):
    text = _fetch(RELEASE_NOTES_INDEX_URL)
    entries = parse_release_notes_table(text)

    out_path = os.path.join(cache_dir, "known_releases.json")
    payload = {
        "source_url": RELEASE_NOTES_INDEX_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "releases": entries,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"  [fetch] release notes table -> {out_path} ({len(entries)} entries)", file=sys.stderr)
    if not entries:
        print("  [warn] 0 entries parsed — table format may have changed, "
              "check the raw markdown before trusting downstream results", file=sys.stderr)
    return out_path


# ============================================================================
# 3. CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', default=DEFAULT_CACHE_DIR)
    parser.add_argument('--spec-only', action='store_true')
    parser.add_argument('--releases-only', action='store_true')
    args = parser.parse_args()

    os.makedirs(args.cache_dir, exist_ok=True)

    if not args.releases_only:
        fetch_pre_dig_spec(args.cache_dir)
    if not args.spec_only:
        fetch_release_notes(args.cache_dir)


if __name__ == '__main__':
    main()
