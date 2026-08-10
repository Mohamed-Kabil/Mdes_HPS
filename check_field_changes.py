#!/usr/bin/env python3
"""
check_field_changes.py — checks every field listed in api_field_changes.md
against BOTH pre-dig.yaml (Mastercard's pre-release note export) and
data.yaml (the current PowerCard Connect API spec), endpoint by endpoint.

Built on top of diff_predig_vs_data.py's loader/$ref-resolver/flattener (same
engine, reused as a library rather than duplicated) — this script answers a
narrower question than the full diff: "for THESE SPECIFIC new/changed
fields Mastercard announced, does each side actually have them?" rather than
"what's every divergence between the two files."

Matching strategy (fields are given in api_field_changes.md as
'->'-separated PascalCase paths, e.g.
'FundingAccountInfo->EncryptedPayload->EncryptedData->SourceTokenNumber',
which don't literally match either file's camelCase property names or exact
nesting, since the note is a human-written summary, not machine-generated):
  1. Flatten the resolved request+response schema of the matching endpoint
     in each source into dotted field paths (reusing flatten_schema).
  2. Normalize every path segment: lowercase, strip non-alphanumerics, and
     fold the 'cypher'/'cipher' spelling variants together (the note spells
     it "algorithmCypherMode"; both files spell it "algorithmCipherMode").
  3. A field from the note is FOUND if some flattened key's LAST segment
     normalizes to the same string as the note's last segment (the leaf
     field name) -- e.g. 'sourceTokenNumber' must appear as a leaf
     somewhere in that endpoint's schema.
  4. Among leaf matches, mark CHAIN_OK if every earlier segment of the
     note's path also appears (in order, as a substring) somewhere in the
     matched key's full dotted path -- this catches leaf-name collisions
     that are actually unrelated fields nested elsewhere.
  5. If no leaf match at all: ABSENT.

This is deliberately a heuristic, human-in-the-loop-friendly check, not a
strict schema equality test -- it is meant to be eyeballed alongside the
printed full matched path, not trusted blindly. A field reported ABSENT is
reliable (no such leaf name exists anywhere in that endpoint's schema on
that side); a field reported FOUND should be spot-checked once against the
printed path if the field name is generic (e.g. 'value', 'type').

Usage:
    python3 check_field_changes.py
        [--changes api_field_changes.md]
        [--pre-dig pre-dig.yaml] [--data data.yaml]
        [-o field_changes_report.json]
"""

import argparse
import os
import json
import re
import sys

from diff_predig_vs_data import (
    load_spec, get_operation, extract_request_schema,
    extract_response_schemas, flatten_schema,
)

# ============================================================================
# 1. Endpoint name (as used in api_field_changes.md section headers) -> path
# ============================================================================

ENDPOINT_TO_PATH = {
    'RequestActivationMethods': '/requestActivationMethods',
    'DeliverActivationCode': '/deliverActivationCode',
    'AuthoriseService': '/authorizeService',
    'AuthorizeService': '/authorizeService',
    'Notify Service Activated': '/notifyServiceActivated',
    'NotifyServiceActivated': '/notifyServiceActivated',
    'NotifyTokenUpdated': '/notifyTokenUpdated',
}

DEFAULT_METHOD = 'post'


# ============================================================================
# 2. api_field_changes.md parsing
# ============================================================================

SECTION_RE = re.compile(r'^##\s+(.+?)\s*$')
TABLE_ROW_RE = re.compile(r'^\|(.+)\|\s*$')


def parse_changes_md(path):
    """Returns [{'endpoint': str, 'field_path': str, 'change_type': str,
    'comment': str}, ...] by reading the '## Endpoint' sections and their
    '| Field Path | Change Type | Comment |' tables."""
    entries = []
    current_endpoint = None
    in_table = False
    with open(path, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')
            m = SECTION_RE.match(line)
            if m:
                current_endpoint = m.group(1).strip()
                in_table = False
                continue
            if not line.strip().startswith('|'):
                in_table = False
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not cells or cells[0].lower() == 'field path':
                in_table = True
                continue
            if set(cells[0]) <= {'-'}:
                continue  # markdown header separator row
            if not in_table or current_endpoint is None:
                continue
            if len(cells) < 2:
                continue
            field_path, change_type = cells[0], cells[1]
            comment = cells[2] if len(cells) > 2 else ''
            entries.append({
                'endpoint': current_endpoint,
                'field_path': field_path,
                'change_type': change_type,
                'comment': comment,
            })
    return entries


# ============================================================================
# 3. Normalization + matching
# ============================================================================

def normalize_segment(seg):
    """lowercase, strip non-alphanumerics, fold cypher->cipher spelling."""
    s = re.sub(r'[^a-z0-9]', '', seg.lower())
    return s.replace('cypher', 'cipher')


def flatten_endpoint(spec, path, method=DEFAULT_METHOD):
    """Flatten BOTH request and response schemas of one endpoint in one
    spec into a single {dotted_path: info} dict, keys prefixed
    'request.'/'response[code].' same as diff_predig_vs_data.py."""
    op = get_operation(spec, path, method)
    if op is None:
        return {}
    fields = {}
    req_schema, _ = extract_request_schema(op, spec)
    if req_schema:
        for k, v in flatten_schema(req_schema).items():
            fields[f'request.{k}'] = v
    for code, schema in extract_response_schemas(op, spec).items():
        if schema:
            for k, v in flatten_schema(schema).items():
                fields[f'response[{code}].{k}'] = v
    return fields


def leaf_equal(a, b):
    """Equal ignoring a trailing plural 's' (the note says 'reasonCode',
    both real schemas say 'reasonCodes'; also handles the reverse)."""
    return a == b or a.rstrip('s') == b.rstrip('s')


def find_matches(note_field_path, flat_fields):
    """note_field_path: 'FundingAccountInfo->EncryptedPayload->...->Leaf'
    (arrow-separated, per api_field_changes.md), a bare 'leafName', or a
    dotted 'activationMethod.type' path — split on BOTH '->' and '.' since
    the note isn't consistent about which separator it uses.
    Returns list of (full_dotted_key, chain_ok:bool)."""
    segments = [s.strip() for s in re.split(r'->|\.', note_field_path) if s.strip()]
    norm_segments = [normalize_segment(s) for s in segments]
    leaf = norm_segments[-1]
    parents = norm_segments[:-1]

    matches = []
    for key in flat_fields:
        key_segments = re.split(r'[.\[\]]+', key)
        key_segments = [s for s in key_segments if s]
        norm_key_segments = [normalize_segment(s) for s in key_segments]
        if not norm_key_segments or not leaf_equal(norm_key_segments[-1], leaf):
            continue
        # chain check: every parent segment must appear (in order) among
        # the earlier key segments (substring match per segment)
        chain_ok = True
        ptr = 0
        for p in parents:
            found_at = None
            for i in range(ptr, len(norm_key_segments) - 1):
                if p in norm_key_segments[i] or norm_key_segments[i] in p:
                    found_at = i
                    break
            if found_at is None:
                chain_ok = False
                break
            ptr = found_at + 1
        matches.append((key, chain_ok))
    return matches


# ============================================================================
# 4. Report
# ============================================================================

def verdict_for(matches):
    if not matches:
        return 'ABSENT'
    if any(chain_ok for _, chain_ok in matches):
        return 'PRESENT'
    return 'PRESENT (leaf name matches, but nesting differs — verify by hand)'


def run(changes_path, predig_path, data_path, output_path, repair=True):
    entries = parse_changes_md(changes_path)
    print(f"  [load] parsed {len(entries)} field entries from {changes_path}", file=sys.stderr)

    print(f"  [load] pre_dig <- {predig_path}", file=sys.stderr)
    predig_spec = load_spec(predig_path, repair=repair)
    print(f"  [load] data <- {data_path}", file=sys.stderr)
    data_spec = load_spec(data_path, repair=repair)

    endpoint_cache = {}

    def get_flat(spec, path):
        cache_key = (id(spec), path)
        if cache_key not in endpoint_cache:
            endpoint_cache[cache_key] = flatten_endpoint(spec, path)
        return endpoint_cache[cache_key]

    results = []
    for entry in entries:
        path = ENDPOINT_TO_PATH.get(entry['endpoint'])
        if path is None:
            print(f"  [warn] unknown endpoint '{entry['endpoint']}' — skipping "
                  f"'{entry['field_path']}'", file=sys.stderr)
            continue

        predig_fields = get_flat(predig_spec, path)
        data_fields = get_flat(data_spec, path)

        predig_matches = find_matches(entry['field_path'], predig_fields)
        data_matches = find_matches(entry['field_path'], data_fields)

        results.append({
            'endpoint': entry['endpoint'],
            'path': path,
            'field_path': entry['field_path'],
            'change_type': entry['change_type'],
            'comment': entry['comment'],
            'pre_dig': {
                'verdict': verdict_for(predig_matches),
                'matched_paths': [k for k, _ in predig_matches],
            },
            'data': {
                'verdict': verdict_for(data_matches),
                'matched_paths': [k for k, _ in data_matches],
            },
        })

    # console report
    for r in results:
        flag = '' if r['data']['verdict'] != 'ABSENT' else '  <-- MISSING IN data.yaml'
        print(f"\n[{r['endpoint']}] {r['field_path']}  ({r['change_type']}){flag}")
        print(f"    pre_dig: {r['pre_dig']['verdict']}"
              + (f"  {r['pre_dig']['matched_paths']}" if r['pre_dig']['matched_paths'] else ''))
        print(f"    data   : {r['data']['verdict']}"
              + (f"  {r['data']['matched_paths']}" if r['data']['matched_paths'] else ''))

    missing_in_data = [r for r in results if r['data']['verdict'] == 'ABSENT']
    missing_in_predig = [r for r in results if r['pre_dig']['verdict'] == 'ABSENT']
    print(f"\n--- TOTAL: {len(results)} field(s) checked ---")
    print(f"    ABSENT in data.yaml   : {len(missing_in_data)}")
    print(f"    ABSENT in pre-dig.yaml: {len(missing_in_predig)}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull report written to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Check every field in api_field_changes.md against pre-dig.yaml and data.yaml."
    )
    parser.add_argument('--changes', default='api_field_changes.md')
    parser.add_argument('--pre-dig', default='pre-dig.yaml')
    parser.add_argument('--data', default=os.environ.get('DATA_YAML_PATH', r'C:\Users\moham\Desktop\input\data.yaml'))
    parser.add_argument('-o', '--output', default='field_changes_report.json')
    parser.add_argument('--no-repair', action='store_true',
                         help="Never attempt the YAML indentation repair pass")
    args = parser.parse_args()

    run(args.changes, args.pre_dig, args.data, args.output, repair=not args.no_repair)


if __name__ == '__main__':
    main()
