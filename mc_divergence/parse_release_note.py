#!/usr/bin/env python3
"""
parse_release_note.py — turns one Mastercard MDES pre-release note (already
fetched as Markdown, per the '/index.md' trick — see fetch_mc_source.py)
into the structured record consumed by phase1_historical_audit.py /
phase2_job_a_new_release_alert.py:

{
  "version": "", "mdes_release": "", "published_date": "",
  "impacted_apis": [], "timeline": {"mtf_date": "", "production_date": ""},
  "changes": [
    {"title": "", "description": "", "endpoints": [],
     "fields": [{"name": "", "description": "", "type": "", "min": "",
                 "max": "", "required": true|false|null, "required_raw": ""}]}
  ]
}

Why this isn't a single fixed regex: 8 real notes (Jan/Mar/Jun/Aug/Oct 2025,
Mar/May/Jun 2026 — see cache/notes_raw/) were pulled to calibrate this, and
NONE of them share the exact same shape:

  - table columns vary: `Field|Description|Type|Required`,
    `Field|Type|Min|Max|Required`, or a single merged
    `Field and Description` column with the name bolded at the start of the
    cell (`**fieldName** rest of the description...`)
  - endpoint association varies: a single `API Reference:` line right after
    a table, several `API Reference:` lines repeated back to back (each a
    single endpoint) applying to the SAME preceding table, or one
    `API References:` (plural) bullet list naming several endpoints that all
    share one table
  - some changes have NO table at all — just prose naming a bolded
    parameter, or a bare bullet list of field names with no type/required
    info (e.g. "the following parameters of the cardAccountDataSchema
    object: * accountNumber * expiryMonth * expiryYear")
  - some reference/lookup tables (e.g. a decline-reason-code -> auth-code
    mapping) are NOT field-change tables and must be skipped — recognized
    because their first column header isn't "Field"/"Field and Description"
  - release dates can be struck through MORE THAN ONCE as a date slips
    twice (`~~10 June 2026~~ ~~1 July 2026~~ 8 July 2026`) — only the last,
    un-struck token is the effective date

Given that spread, this parses what it can recognize (field-tables with a
"Field..." first column, `API Reference(s):` markers, `~~..~~`-aware dates)
and organizes changes by the innermost numbered/"Change N" heading. Anything
a note doesn't offer (no table, no endpoint marker) is left as an empty list
rather than guessed — a change with fields=[] and endpoints=[] still carries
its title/description, which is enough for a human to read in the report.

A note where NOTHING recognizable was found anywhere (no field-table, no
endpoint marker at all) is dumped verbatim to
cache/unparsed_notes/<slug>.md for manual structuring, per the agreed
fallback strategy — this script does not call out to an LLM.

Usage:
    python3 parse_release_note.py cache/notes_raw/prereleasenote_taf_jan25.md \
        --url https://developer.mastercard.com/.../index.md
    python3 parse_release_note.py --all cache/notes_raw/ -o cache/parsed_notes.json
"""

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
UNPARSED_DIR_NAME = "unparsed_notes"

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
ANCHOR_SUFFIX_RE = re.compile(r'\s*\{#[^}]+\}\s*$')  # strips '{#some-anchor}'
CHANGE_HEADING_RE = re.compile(r'(?i)\bchange\s*\d+\b|^\d+\.\d+\b')
BOLD_FIELD_RE = re.compile(r'^(?:\*\*(.+?)\*\*|`(.+?)`)\s*(.*)$', re.DOTALL)
STRIKETHROUGH_RE = re.compile(r'~~.*?~~')
API_REF_MARKER_RE = re.compile(r'(?i)API\s+References?\s*:')
ENDPOINT_RE = re.compile(r'`(GET|POST|PUT|DELETE|PATCH)\s+([^`]+?)`')

# Fixed, exact-match vocabulary of API display names -> real path, as seen
# consistently in "Impacted API(s)" summaries across the 8 notes used to
# calibrate this parser. Used ONLY as a last-resort fallback when a change
# has no 'API Reference' marker anywhere in its own or its parent's section
# (happens when a note states the API once at the top and never repeats an
# explicit endpoint per sub-change) — never used to override/guess over an
# explicit marker that IS present.
API_DISPLAY_NAME_TO_PATH = {
    'authorize service': '/authorizeService',
    'authorize service (as)': '/authorizeService',
    'request activation methods': '/requestActivationMethods',
    'request activation methods (ram)': '/requestActivationMethods',
    'deliver activation code': '/deliverActivationCode',
    'deliver activation code (dac)': '/deliverActivationCode',
    'notify service activated': '/notifyServiceActivated',
    'notify service activated (nsa)': '/notifyServiceActivated',
    'notify token updated': '/notifyTokenUpdated',
    'notify token updated (ntu)': '/notifyTokenUpdated',
    'validate activation code': '/validateActivationCode',
    'get account information': '/getAccountInformation',
    'notify suspicious events': '/notifySuspiciousEvents',
}


def map_impacted_apis_to_paths(impacted_apis):
    paths = []
    for name in impacted_apis:
        key = re.sub(r'\s+', ' ', name).strip().lower()
        path = API_DISPLAY_NAME_TO_PATH.get(key)
        if path and path not in paths:
            paths.append(path)
    return paths
DATE_LINE_RE = re.compile(r'(?i)^\*?\s*(MTF|Production)\s*[:\-]\s*(.+)$')
TABLE_ROW_SPLIT_RE = re.compile(r'(?<!\\)\|')
SEPARATOR_ROW_RE = re.compile(r'^[\s|:-]+$')


# ============================================================================
# 1. Heading tree -> flat list of (line_index, level, text)
# ============================================================================

def find_headings(lines):
    headings = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = ANCHOR_SUFFIX_RE.sub('', m.group(2)).strip()
            headings.append((i, level, text))
    # Stop before '## Impact' (and everything after): several notes restate
    # "### Change 1" / "### Change 2" as sub-headings THERE purely to narrate
    # business impact, reusing the exact same titles as the real technical
    # changes above — left unfiltered, those get picked up as bogus empty
    # duplicate changes. Nothing field/endpoint-bearing has ever appeared
    # at or after 'Impact' in any of the 8 notes used to calibrate this.
    for idx, (_, _, text) in enumerate(headings):
        if text.strip().lower() == 'impact':
            return headings[:idx]
    return headings


def section_bounds(headings, idx):
    """End line (exclusive) of the section starting at headings[idx]:
    the next heading at the SAME level or shallower."""
    _, level, _ = headings[idx]
    for j in range(idx + 1, len(headings)):
        if headings[j][1] <= level:
            return headings[j][0]
    return None  # runs to end of document


# ============================================================================
# 2. Dates ("~~superseded~~ effective", possibly chained twice)
# ============================================================================

def parse_date_field(raw_value):
    """'~~10 June 2026~~ ~~1 July 2026~~ 8 July 2026' ->
    {'effective': '8 July 2026', 'superseded': ['10 June 2026', '1 July 2026']}"""
    superseded = [s.strip() for s in STRIKETHROUGH_RE.findall(raw_value)]
    # STRIKETHROUGH_RE.findall gives the '~~...~~' spans WITH the tildes since
    # the pattern itself has no capture group; re-extract inner text instead.
    superseded = [re.sub(r'^~~|~~$', '', s).strip() for s in
                  re.findall(r'~~.*?~~', raw_value)]
    effective = STRIKETHROUGH_RE.sub('', raw_value).strip()
    return {'effective': effective, 'superseded': superseded}


def extract_timeline(full_text):
    timeline = {}
    for line in full_text.splitlines():
        m = DATE_LINE_RE.match(line.strip())
        if not m:
            continue
        label, raw_value = m.group(1).lower(), m.group(2)
        timeline[label] = parse_date_field(raw_value)
    return {
        'mtf_date': timeline.get('mtf', {}).get('effective'),
        'mtf_superseded': timeline.get('mtf', {}).get('superseded', []),
        'production_date': timeline.get('production', {}).get('effective'),
        'production_superseded': timeline.get('production', {}).get('superseded', []),
    }


# ============================================================================
# 3. Impacted APIs (top-of-note summary list, not per-change)
# ============================================================================

def extract_impacted_apis(full_text):
    """Finds the bullet list right after any '...Impacted API...' marker
    (heading or bold inline text) near the top of the note."""
    lines = full_text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r'(?i)impacted\s+api', line):
            apis = []
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if not s:
                    if apis:
                        break
                    continue
                bullet_m = re.match(r'^[*-]\s+(.+)$', s)
                if bullet_m:
                    apis.append(bullet_m.group(1).strip())
                    continue
                break
            if apis:
                return apis
    return []


# ============================================================================
# 4. Field tables (flexible header) + endpoint markers, per change-section
# ============================================================================

def _split_row(line):
    cells = TABLE_ROW_SPLIT_RE.split(line.strip())
    cells = [c.strip() for c in cells]
    if cells and cells[0] == '':
        cells = cells[1:]
    if cells and cells[-1] == '':
        cells = cells[:-1]
    return cells


def find_table_blocks(text):
    """Returns list of (header_cells, [row_cells, ...]) for every markdown
    pipe-table in `text`, in document order."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('|'):
            header = _split_row(lines[i])
            j = i + 1
            if j < len(lines) and SEPARATOR_ROW_RE.match(lines[j].strip()) and '-' in lines[j]:
                j += 1
                rows = []
                while j < len(lines) and lines[j].strip().startswith('|'):
                    rows.append(_split_row(lines[j]))
                    j += 1
                blocks.append((header, rows))
                i = j
                continue
        i += 1
    return blocks


def _map_columns(header):
    """header cells (already lowercased by caller) -> index map, or None if
    this isn't a field-change table (first column must mention 'field')."""
    lower = [h.lower() for h in header]
    if not lower or 'field' not in lower[0]:
        return None
    col = {'field': 0, 'field_has_description': 'description' in lower[0]}
    for idx, name in enumerate(lower):
        if idx == 0:
            continue
        if 'description' in name:
            col['description'] = idx
        elif 'min' in name and 'length' in name:
            col['min'] = idx
        elif 'max' in name and 'length' in name:
            col['max'] = idx
        elif 'required' in name:
            col['required'] = idx
        elif 'data type' in name or name.strip() == 'type':
            col['type'] = idx
    return col


def _cell(row, idx):
    return row[idx].strip() if idx is not None and idx < len(row) else None


def _required_bool(raw):
    if raw is None:
        return None
    s = raw.strip().lower()
    if s.startswith('yes') or s.startswith('required'):
        return True
    if s.startswith('no') or s.startswith('optional'):
        return False
    return None  # "Conditional ..." — genuinely neither, kept as required_raw


def parse_fields_from_table(header, rows):
    col = _map_columns(header)
    if col is None:
        return None  # not a field-change table (e.g. a code lookup table) — skip
    fields = []
    for row in rows:
        field_cell = _cell(row, col['field']) or ''
        description = _cell(row, col.get('description'))
        if col.get('field_has_description'):
            m = BOLD_FIELD_RE.match(field_cell)
            if m:
                name = (m.group(1) or m.group(2)).strip()
                desc_from_cell = m.group(3).strip()
                description = desc_from_cell or description
            else:
                name = field_cell
        else:
            name = re.sub(r'\*\*', '', field_cell).strip()
        required_raw = _cell(row, col.get('required'))
        fields.append({
            'name': name,
            'description': description,
            'type': _cell(row, col.get('type')),
            'min': _cell(row, col.get('min')),
            'max': _cell(row, col.get('max')),
            'required': _required_bool(required_raw),
            'required_raw': required_raw,
        })
    return fields


def extract_endpoints(text):
    """All `METHOD /path` occurrences following an 'API Reference(s):'
    marker anywhere in `text` (covers single-line, repeated-single-line, and
    plural-bullet-list styles alike — the marker's exact cardinality doesn't
    matter once we're just scanning for backtick-quoted endpoints after it)."""
    idx = 0
    endpoints = []
    seen = set()
    while True:
        m = API_REF_MARKER_RE.search(text, idx)
        if not m:
            break
        # scan forward until the next heading-level break or ~400 chars,
        # whichever first, to avoid slurping unrelated later endpoints
        window = text[m.end(): m.end() + 400]
        stop = window.find('\n\n\n')
        if stop != -1:
            window = window[:stop]
        for em in ENDPOINT_RE.finditer(window):
            ep = f"{em.group(1)} {em.group(2).strip()}"
            if ep not in seen:
                seen.add(ep)
                endpoints.append(ep)
        idx = m.end()
    return endpoints


# ============================================================================
# 5. Change sections (innermost "Change N" / "N.N ..." headings only)
# ============================================================================

def _is_change_heading(text):
    return bool(CHANGE_HEADING_RE.search(text))


def find_leaf_change_headings(headings):
    """Keep only change-headings that have no OTHER change-heading nested
    inside their own section bounds (avoids double-counting a parent
    'Change 1' whose real content lives in child '1.1'/'1.2' subsections)."""
    change_idxs = [i for i, (_, _, text) in enumerate(headings) if _is_change_heading(text)]
    leaves = []
    for i in change_idxs:
        line_idx, level, _ = headings[i]
        end = section_bounds(headings, i)
        has_nested_change = any(
            headings[j][0] > line_idx and (end is None or headings[j][0] < end)
            for j in change_idxs if j != i
        )
        if not has_nested_change:
            leaves.append(i)
    return leaves


def _nearest_enclosing_change(headings, change_idxs, leaf_idx):
    """The closest change-heading (possibly not a leaf itself, e.g. a parent
    '## Change 1' whose real content lives in child '### 1.1'/'1.2') whose
    section bounds strictly contain leaf_idx's heading line. Used to inherit
    an 'API Reference' that was only stated once at the parent level (e.g.
    "The Authorize service will be enhanced as follows: ..." followed by
    1.1/1.2/1.3 subsections that share one API Reference at the very end)."""
    leaf_line = headings[leaf_idx][0]
    best = None
    for j in change_idxs:
        if j == leaf_idx:
            continue
        j_line, j_level, _ = headings[j]
        if j_line >= leaf_line:
            continue
        end = section_bounds(headings, j)
        if end is not None and leaf_line >= end:
            continue
        if best is None or j_line > headings[best][0]:
            best = j
    return best


def extract_changes(full_text, lines, headings, impacted_apis=None):
    change_idxs = [i for i, (_, _, text) in enumerate(headings) if _is_change_heading(text)]
    changes = []
    for i in find_leaf_change_headings(headings):
        line_idx, level, title = headings[i]
        end = section_bounds(headings, i)
        section_text = '\n'.join(lines[line_idx + 1: end if end is not None else len(lines)])

        table_blocks = find_table_blocks(section_text)
        fields = []
        for header, rows in table_blocks:
            parsed = parse_fields_from_table(header, rows)
            if parsed:
                fields.extend(parsed)

        endpoints = extract_endpoints(section_text)
        if not endpoints:
            # fall back to the nearest enclosing parent change-heading's own
            # text (e.g. a shared intro naming the API once for several
            # numbered subsections, or a single API Reference stated only
            # at the end of the parent's combined section)
            parent = _nearest_enclosing_change(headings, change_idxs, i)
            if parent is not None:
                p_line, p_level, _ = headings[parent]
                p_end = section_bounds(headings, parent)
                parent_text = '\n'.join(lines[p_line + 1: p_end if p_end is not None else len(lines)])
                endpoints = extract_endpoints(parent_text)
        endpoints_inferred = False
        if not endpoints and impacted_apis:
            inferred = map_impacted_apis_to_paths(impacted_apis)
            if inferred:
                endpoints = [f"(inferred) {p}" for p in inferred]
                endpoints_inferred = True

        # description = text before the first table/bullet/heading-marker noise
        desc_lines = []
        for l in section_text.splitlines():
            s = l.strip()
            if s.startswith('|') or s.startswith('API Reference') or not s:
                if desc_lines:
                    break
                continue
            desc_lines.append(s)
        description = ' '.join(desc_lines).strip()

        changes.append({
            'title': title,
            'description': description,
            'endpoints': endpoints,
            'endpoints_inferred': endpoints_inferred,
            'fields': fields,
        })
    return changes


# ============================================================================
# 6. Top-level parse
# ============================================================================

def parse_note(markdown_text, url=None):
    text = markdown_text
    # strip a ```markdown fence if WebFetch-style wrapping is present
    fence_m = re.match(r'^```(?:markdown)?\s*\n(.*)\n```\s*$', text.strip(), re.DOTALL)
    if fence_m:
        text = fence_m.group(1)
    lines = text.splitlines()

    title_line = next((l for l in lines if l.startswith('# ')), '')
    version = ANCHOR_SUFFIX_RE.sub('', title_line[2:]).strip()

    headings = find_headings(lines)
    impacted_apis = extract_impacted_apis(text)
    changes = extract_changes(text, lines, headings, impacted_apis=impacted_apis)

    record = {
        'url': url,
        'version': version,
        'mdes_release': None,   # filled in by the caller from known_releases.json
        'published_date': None,  # ditto
        'impacted_apis': impacted_apis,
        'timeline': extract_timeline(text),
        'changes': changes,
    }

    has_signal = any(c['fields'] or c['endpoints'] for c in changes)
    record['_parse_status'] = 'ok' if (changes and has_signal) else 'low_confidence'
    return record


def parse_note_file(path, url=None, cache_dir=DEFAULT_CACHE_DIR):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    record = parse_note(text, url=url)
    if record['_parse_status'] == 'low_confidence':
        unparsed_dir = os.path.join(cache_dir, UNPARSED_DIR_NAME)
        os.makedirs(unparsed_dir, exist_ok=True)
        dest = os.path.join(unparsed_dir, os.path.basename(path))
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"  [fallback] '{path}' had no recognizable field-table or endpoint "
              f"marker -> dumped to {dest} for manual structuring", file=sys.stderr)
    return record


# ============================================================================
# 7. CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('path', help="a single note .md file, or a directory when --all is used")
    parser.add_argument('--url', help="source URL to embed in the record (single-file mode)")
    parser.add_argument('--all', action='store_true', help="treat `path` as a directory of *.md files")
    parser.add_argument('-o', '--output', help="write JSON here instead of stdout")
    parser.add_argument('--cache-dir', default=DEFAULT_CACHE_DIR)
    args = parser.parse_args()

    if args.all:
        records = []
        for fp in sorted(glob.glob(os.path.join(args.path, '*.md'))):
            records.append(parse_note_file(fp, cache_dir=args.cache_dir))
        result = records
    else:
        result = parse_note_file(args.path, url=args.url, cache_dir=args.cache_dir)

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == '__main__':
    main()
