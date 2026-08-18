#!/usr/bin/env python3
"""
visa_installments_presence_check.py — for each endpoint in openapi_full.json
(Visa Installment Solutions Seller API), checks whether an endpoint of the
same identity exists in mc_divergence/data.yaml (PowerCARD-Acquirer, 150+
web services). Presence only, right now -- no field-level diff (see "Next
step" below).

Matching, two passes, since the two specs don't share a naming convention
at all (Visa's own paths are lowercase/slash-segmented, e.g.
'/installments/v2/devices'; PowerCARD's internal names for the SAME domain
are PascalCase and prefixed 'Vis', e.g. '/VisPlanCancellation/V2' — the
'Vis' prefix is what PowerCARD uses internally to mark "this implements a
Visa-side capability", it's not in Visa's own public spec at all):

  1. Exact pass — diff_openapi_all.normalize_path_key() (already built,
     reused not reimplemented): strips version segments + punctuation,
     lowercases. Only catches paths that happen to share the same words in
     the same order.
  2. Fuzzy pass (used when the exact pass finds nothing) — tokenizes both
     sides into word sets (splitting camelCase/PascalCase and path
     segments, stripping the 'Vis' prefix before tokenizing the data.yaml
     side) and scores every '/Vis*/' endpoint by Jaccard overlap
     (path + operationId + summary vs the data.yaml path's own words).
     Best candidate above FUZZY_MATCH_THRESHOLD is reported as a probable
     match — NOT a confirmed one. This is a heuristic, same spirit as
     check_field_changes.py's leaf-name matching elsewhere in this repo:
     meant to be eyeballed via the printed word overlap, not trusted blindly.

One entry in openapi_full.json, '{postbackNotificationUrl}', is a malformed
path in the source spec itself (a path *parameter placeholder* used as the
literal path, not embedded in a real path) -- flagged separately.

Next step (not done here, per the "right now only check presence" ask):
once a match is confirmed by eye, diff request/response fields the same way
check_field_changes.py / mdes_cs_divergence_report.py do for the other two
domains.

Usage:
    python3 visa_installments_presence_check.py
        [--openapi openapi_full.json] [--data mc_divergence/data.yaml]
        [-o visa_installments_presence_report.json]
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'mc_divergence'))

from diff_openapi_all import load_spec, normalize_path_key

DEFAULT_OPENAPI = os.path.join(HERE, 'openapi_full.json')
DEFAULT_DATA = os.path.join(HERE, 'mc_divergence', 'data.yaml')
DEFAULT_OUTPUT = os.path.join(HERE, 'visa_installments_presence_report.json')

FUZZY_MATCH_THRESHOLD = 0.3
STOPWORDS = {'api', 'v1', 'v2', 'the', 'for', 'post', 'get', 'put'}


def load_openapi_paths(path):
    with open(path, encoding='utf-8') as f:
        spec = json.load(f)
    return spec.get('paths', {}), spec.get('info', {})


def tokenize(text):
    text = re.sub(r'[{}/_-]', ' ', text)
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    return {w.lower() for w in text.split() if len(w) > 2 and w.lower() not in STOPWORDS}


def build_vis_token_index(data_spec):
    """Every top-level data.yaml path whose first segment starts with
    'Vis' (case-insensitive) -- PowerCARD's own marker for a Visa-domain
    endpoint -- tokenized with that prefix stripped."""
    index = {}
    for p in data_spec.get('paths', {}):
        first_segment = p.strip('/').split('/')[0]
        if first_segment.lower().startswith('vis'):
            index[p] = tokenize(first_segment[3:])
    return index


def check_presence(openapi_paths, data_spec):
    data_by_norm = {}
    for p in data_spec.get('paths', {}):
        data_by_norm.setdefault(normalize_path_key(p), []).append(p)
    vis_tokens = build_vis_token_index(data_spec)

    results = []
    for path, methods in openapi_paths.items():
        malformed = path.startswith('{') and path.endswith('}')
        norm = normalize_path_key(path.strip('{}')) if malformed else normalize_path_key(path)
        exact_matches = data_by_norm.get(norm)

        for method, op in methods.items():
            entry = {
                'path': path, 'method': method.upper(), 'malformed_path': malformed,
                'operation_id': op.get('operationId'), 'summary': op.get('summary'),
            }
            if exact_matches:
                entry.update({'status': 'present_exact', 'matched_data_yaml_paths': exact_matches})
                results.append(entry)
                continue

            query_tokens = tokenize(path) | tokenize(op.get('operationId') or '') | tokenize(op.get('summary') or '')
            scored = []
            for vis_path, vtoks in vis_tokens.items():
                overlap = query_tokens & vtoks
                if not overlap:
                    continue
                score = len(overlap) / len(query_tokens | vtoks)
                scored.append((score, vis_path, sorted(overlap)))
            scored.sort(reverse=True)

            if scored and scored[0][0] >= FUZZY_MATCH_THRESHOLD:
                entry.update({
                    'status': 'present_fuzzy',
                    'matched_data_yaml_paths': [scored[0][1]],
                    'match_score': round(scored[0][0], 2), 'match_overlap_words': scored[0][2],
                    'other_candidates': [{'path': p, 'score': round(s, 2), 'overlap': o} for s, p, o in scored[1:3]],
                })
            else:
                entry.update({
                    'status': 'absent', 'matched_data_yaml_paths': [],
                    'other_candidates': [{'path': p, 'score': round(s, 2), 'overlap': o} for s, p, o in scored[:3]],
                })
            results.append(entry)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--openapi', default=DEFAULT_OPENAPI)
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    openapi_paths, info = load_openapi_paths(args.openapi)
    data_spec = load_spec(args.data, repair=True)
    results = check_presence(openapi_paths, data_spec)

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1

    print(f"  [check] {info.get('title', '?')} — {len(results)} endpoint(s) au total", file=sys.stderr)
    print(f"  [check] {counts.get('present_exact', 0)} présent(s) (exact), "
          f"{counts.get('present_fuzzy', 0)} probable(s) (fuzzy — à vérifier à l'oeil), "
          f"{counts.get('absent', 0)} absent(s)", file=sys.stderr)
    for r in results:
        flag = '  [chemin malformé dans le spec source]' if r['malformed_path'] else ''
        if r['status'] == 'present_exact':
            status = f"PRÉSENT (exact) -> {r['matched_data_yaml_paths']}"
        elif r['status'] == 'present_fuzzy':
            status = (f"PROBABLE ({r['match_score']}) -> {r['matched_data_yaml_paths'][0]} "
                      f"[mots communs: {', '.join(r['match_overlap_words'])}]")
        else:
            best = r['other_candidates'][0] if r['other_candidates'] else None
            status = f"ABSENT" + (f" (meilleur candidat rejeté : {best['path']} @ {best['score']})" if best else "")
        print(f"    {r['method']:6} {r['path']:60} {status}{flag}", file=sys.stderr)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump({
            'openapi_source': args.openapi, 'data_source': args.data,
            'openapi_title': info.get('title'), 'openapi_version': info.get('version'),
            'total': len(results), 'counts': counts,
            'fuzzy_match_threshold': FUZZY_MATCH_THRESHOLD,
            'results': results,
        }, f, indent=2, ensure_ascii=False)
    print(f"[report] {args.output}", file=sys.stderr)


if __name__ == '__main__':
    main()
