#!/usr/bin/env python3
"""
field_changes_vs_data_report.py — targeted alternative to the note-parsing
approach in phase1_historical_audit.py: instead of comparing text extracted
from each individual release note, this takes the human-curated
api_field_changes.md (one row per field HPS already identified as changed
since January 2025, grouped by endpoint), resolves each field's REAL
definition (type/minLength/maxLength/required) directly from pre-dig.yaml
(the live, structured Mastercard spec — reusing check_field_changes.py's
proven leaf-name + parent-chain matching, not fragile note-text parsing),
then compares that definition against data.yaml the same way
phase1_historical_audit.py does (compare_field-style attribute diff).

Why this exists alongside phase1_historical_audit.py: api_field_changes.md
was hand-curated by HPS from reading the actual pre-release notes, so it's
already deduplicated and endpoint-grouped — this sidesteps every parsing
edge case (tables with no Parent info, bold-vs-backtick field names, notes
with no table at all) that phase1's note-parser has to guess around. The
tradeoff: it only covers what's in api_field_changes.md, not every change
mentioned in a note automatically.

Output: overwrites the SAME dated email file
'reports/email divergence date - jj-mm-aa.md' that phase1_historical_audit.py
writes, so downstream consumers (the --send flow) don't need to change.

Usage:
    python3 field_changes_vs_data_report.py
        [--changes api_field_changes.md] [--pre-dig cache/pre-dig.yaml]
        [--data ../data.yaml] [--cutoff-label 2025-01]
"""

import argparse
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from diff_openapi_all import load_spec, get_operation, flatten_schema
from diff_predig_vs_data import extract_request_schema, extract_response_schemas

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CHANGES = os.path.join(HERE, 'api_field_changes.md')
DEFAULT_PREDIG = os.path.join(HERE, 'cache', 'pre-dig.yaml')
DEFAULT_DATA = os.environ.get('DATA_YAML_PATH', r'C:\Users\moham\Desktop\input\data.yaml')

ENDPOINT_TO_PATH = {
    'RequestActivationMethods': '/requestActivationMethods',
    'DeliverActivationCode': '/deliverActivationCode',
    'AuthoriseService': '/authorizeService',
    'AuthorizeService': '/authorizeService',
    'Notify Service Activated': '/notifyServiceActivated',
    'NotifyServiceActivated': '/notifyServiceActivated',
    'NotifyTokenUpdated': '/notifyTokenUpdated',
}
ENDPOINT_DISPLAY = {
    '/requestActivationMethods': 'Request Activation Methods (RAM)',
    '/deliverActivationCode': 'Deliver Activation Code (DAC)',
    '/authorizeService': 'Authorize Service (AS)',
    '/notifyServiceActivated': 'Notify Service Activated (NSA)',
    '/notifyTokenUpdated': 'Notify Token Updated (NTU)',
}

EMAIL_RECIPIENTS = os.environ.get('MC_DIVERGENCE_RECIPIENTS')


# ============================================================================
# 1. api_field_changes.md parsing (identical to check_field_changes.py)
# ============================================================================

SECTION_RE = re.compile(r'^##\s+(.+?)\s*$')


def parse_changes_md(path):
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
                continue
            if not in_table or current_endpoint is None:
                continue
            if len(cells) < 2:
                continue
            field_path, change_type = cells[0], cells[1]
            comment = cells[2] if len(cells) > 2 else ''
            entries.append({'endpoint': current_endpoint, 'field_path': field_path,
                             'change_type': change_type, 'comment': comment})
    return entries


# ============================================================================
# 2. Matching (identical strategy to check_field_changes.py)
# ============================================================================

def normalize_segment(seg):
    s = re.sub(r'[^a-z0-9]', '', seg.lower())
    return s.replace('cypher', 'cipher')


def leaf_equal(a, b):
    return a == b or a.rstrip('s') == b.rstrip('s')


def flatten_endpoint(spec, path, method='post'):
    op = get_operation(spec, path, method)
    if op is None:
        return None
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


def find_matches(note_field_path, flat_fields):
    segments = [s.strip() for s in re.split(r'->|\.', note_field_path) if s.strip()]
    norm_segments = [normalize_segment(s) for s in segments]
    leaf = norm_segments[-1]
    parents = norm_segments[:-1]

    matches = []
    for key in flat_fields:
        key_segments = [s for s in re.split(r'[.\[\]]+', key) if s]
        norm_key_segments = [normalize_segment(s) for s in key_segments]
        if not norm_key_segments or not leaf_equal(norm_key_segments[-1], leaf):
            continue
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


NOTE_TYPE_TO_SCHEMA_TYPE = {
    'string': 'string', 'number': 'integer', 'object': 'object',
    'complexobject': 'object', 'array': 'array', 'arrayofstring': 'array',
}


def compare_attrs(predig_info, data_info):
    """predig_info/data_info: the flatten_schema() info dicts for the
    matched field on each side. Returns (status, reasons[])."""
    reasons = []
    p_type, d_type = predig_info.get('type'), data_info.get('type')
    if p_type and d_type and p_type != d_type:
        reasons.append(f"type: pre-dig.yaml a '{p_type}', data.yaml a '{d_type}'")

    for attr, label in (('maxLength', 'maxLength'), ('minLength', 'minLength')):
        p_val, d_val = predig_info.get(attr), data_info.get(attr)
        if p_val is not None and d_val is not None and p_val != d_val:
            reasons.append(f"{label}: pre-dig.yaml a {p_val}, data.yaml a {d_val}")

    p_req, d_req = bool(predig_info.get('required')), bool(data_info.get('required'))
    if p_req != d_req:
        reasons.append(f"required: pre-dig.yaml a {p_req}, data.yaml a {d_req}")

    return ('partiel' if reasons else 'implemente'), reasons


# ============================================================================
# 3. Report
# ============================================================================

def audit(entries, predig_spec, data_spec):
    endpoint_cache_predig, endpoint_cache_data = {}, {}
    results = []
    for entry in entries:
        path = ENDPOINT_TO_PATH.get(entry['endpoint'])
        if path is None:
            print(f"  [warn] unknown endpoint '{entry['endpoint']}'", file=sys.stderr)
            continue

        if path not in endpoint_cache_predig:
            endpoint_cache_predig[path] = flatten_endpoint(predig_spec, path)
        if path not in endpoint_cache_data:
            endpoint_cache_data[path] = flatten_endpoint(data_spec, path)

        predig_fields = endpoint_cache_predig[path]
        data_fields = endpoint_cache_data[path]

        predig_matches = find_matches(entry['field_path'], predig_fields or {})
        predig_best = next((m for m in predig_matches if m[1]), predig_matches[0]) if predig_matches else None

        if data_fields is None:
            status, reasons = 'non_implemente', ["endpoint absent de data.yaml"]
            data_match_path = None
        else:
            data_matches = find_matches(entry['field_path'], data_fields)
            if not data_matches:
                status, reasons = 'non_implemente', ["aucun champ correspondant trouvé"]
                data_match_path = None
            else:
                data_best = next((m for m in data_matches if m[1]), data_matches[0])
                data_match_path = data_best[0]
                if predig_best:
                    status, reasons = compare_attrs(predig_fields[predig_best[0]], data_fields[data_match_path])
                else:
                    status, reasons = 'implemente', []
                if not data_best[1]:
                    reasons = reasons + ["nom trouvé mais imbrication différente — à vérifier"]

        predig_line = predig_fields[predig_best[0]].get('line') if predig_best else None
        data_line = data_fields[data_match_path].get('line') if (data_fields and data_match_path) else None

        results.append({
            'endpoint': entry['endpoint'], 'path': path,
            'field_path': entry['field_path'], 'change_type': entry['change_type'],
            'comment': entry['comment'],
            'predig_found': predig_best is not None,
            'predig_matched_path': predig_best[0] if predig_best else None,
            'status': status, 'reasons': reasons,
            'data_matched_path': data_match_path,
            'predig_line': predig_line, 'data_line': data_line,
        })
    return results


STATUS_ICON = {'non_implemente': '🔴', 'partiel': '🟡', 'implemente': '🟢'}


def render_email(results, cutoff_label):
    by_endpoint = {}
    for r in results:
        by_endpoint.setdefault(r['path'], []).append(r)

    total = len(results)
    urgent = [r for r in results if r['status'] != 'implemente']

    lines = [
        f"Objet : [MDES] Audit divergences (api_field_changes.md) — {len(urgent)} écart(s) "
        f"à traiter (depuis {cutoff_label})",
        f"À : {EMAIL_RECIPIENTS or '(destinataires non définis — MC_DIVERGENCE_RECIPIENTS)'}",
        "",
        "Bonjour,",
        "",
        f"Nouvelle approche : les {total} champs de api_field_changes.md (curés manuellement depuis "
        f"les pre-release notes Mastercard depuis {cutoff_label}) ont été résolus directement depuis "
        f"pre-dig.yaml (type/longueur/required réels), puis comparés à data.yaml. "
        f"{len(urgent)} écart(s) détecté(s) sur {total} champs vérifiés.",
        "",
        "Le rapport complet (détail par note) reste disponible en pièce jointe habituelle "
        "(phase1_divergence_report.md) pour l'approche par notes individuelles — ceci est un "
        "recoupement indépendant, basé sur la liste déjà validée par HPS.",
        "",
        "### Détail par API",
        "",
    ]

    for path, items in by_endpoint.items():
        display = ENDPOINT_DISPLAY.get(path, path)
        lines.append(f"**{display}**")
        for r in items:
            icon = STATUS_ICON[r['status']]
            reason_txt = '; '.join(r['reasons']) if r['reasons'] else ''
            predig_note = '' if r['predig_found'] else '  [absent de pre-dig.yaml aussi — vérifier api_field_changes.md]'
            suffix = f" ({reason_txt})" if reason_txt else ''
            loc_parts = []
            if r.get('predig_line'):
                loc_parts.append(f"pre-dig.yaml:{r['predig_line']}")
            if r.get('data_line'):
                loc_parts.append(f"data.yaml:{r['data_line']}")
            loc_txt = f" — {', '.join(loc_parts)}" if loc_parts else ''
            lines.append(f"  - {icon} `{r['field_path']}` [{r['change_type']}] : `{r['status']}`{suffix}{predig_note}{loc_txt}")
        lines.append("")

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    lines.append("### Résumé")
    lines.append("")
    lines.append(f"- Implémentés : {counts.get('implemente', 0)}")
    lines.append(f"- Partiels : {counts.get('partiel', 0)}")
    lines.append(f"- Non implémentés : {counts.get('non_implemente', 0)}")
    lines.append(f"- Total vérifié : {total}")

    return '\n'.join(lines)


def default_email_path():
    return os.path.join(HERE, "reports", f"email divergence date - {date.today().strftime('%d-%m-%y')}.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--changes', default=DEFAULT_CHANGES)
    parser.add_argument('--pre-dig', default=DEFAULT_PREDIG)
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--cutoff-label', default='2025-01')
    parser.add_argument('--email', default=None)
    parser.add_argument('--send', action='store_true',
                         help="Actually email the report via SMTP (needs SMTP_HOST/SMTP_USER/"
                              "SMTP_PASSWORD env vars — fails loudly if missing). Without this "
                              "flag, only the local email file is written.")
    args = parser.parse_args()

    email_path = args.email or default_email_path()

    entries = parse_changes_md(args.changes)
    print(f"  [load] {len(entries)} field entries from {args.changes}", file=sys.stderr)

    predig_spec = load_spec(args.pre_dig, repair=True)
    data_spec = load_spec(args.data, repair=True)

    results = audit(entries, predig_spec, data_spec)
    email = render_email(results, args.cutoff_label)

    os.makedirs(os.path.dirname(email_path), exist_ok=True)
    with open(email_path, 'w', encoding='utf-8') as f:
        f.write(email)
    print(f"\n  [write] email écrasé -> {email_path}", file=sys.stderr)

    if args.send:
        import send_email as send_email_module
        subject_line, _, body = email.partition('\n')
        subject = subject_line.removeprefix('Objet : ').strip()
        try:
            sent_to = send_email_module.send_email(subject, email)
            print(f"  [send] email SENT to {', '.join(sent_to)}", file=sys.stderr)
        except send_email_module.SmtpConfigError as e:
            print(f"  [send] email NOT sent — {e}", file=sys.stderr)
            sys.exit(1)

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    print(f"\n--- TOTAL: {len(results)} champ(s) — implemente={counts.get('implemente',0)} "
          f"partiel={counts.get('partiel',0)} non_implemente={counts.get('non_implemente',0)} ---")


if __name__ == '__main__':
    main()
