#!/usr/bin/env python3
"""
mdes_cs_divergence_report.py — compares the official MDES Customer Service
OpenAPI spec (Mastercard's published truth, fetched from
developer.mastercard.com) against what the pwc-api-sp5_api Java codebase
actually builds (extract_java_field_mapping.py's generated output), for the
6 CS operations (Search, Token Activate, Update, Suspend, Unsuspend, Delete).

Same relationship as pre-dig.yaml vs data.yaml in mc_divergence/ — the
official spec plays pre-dig.yaml's role (source of truth for what the API
supports), the Java extraction plays data.yaml's role (what's actually
implemented) — just applied to the CS API domain instead of
Pre-Digitization, and sourced from Java instead of a second spec.

Field matching: exact dotted-path match first (the Java DTOs were built
against this same spec family, so names usually agree exactly), falling
back to last-segment name match tolerant of case and known spelling
variants (see SPELLING_FOLDS — same idea as check_field_changes.py's
cypher/cipher fold).

Per-field status:
  non_implemente  — no Java field found anywhere in any variant
  non_verifiable  — matched, but the Java extraction itself couldn't
                    resolve that field (source: unresolved) — a gap in the
                    input data, not a confirmed absence (see
                    MDES_CS_API_JAVA_MAPPING_LINK.md)
  partiel         — matched via the local LLM's inference rather than a
                    direct mechanical scan (source: llm-inferred)
  implemente      — matched directly by the mechanical scanner

Usage:
    python3 mdes_cs_divergence_report.py
        [--spec C:\\Users\\moham\\Desktop\\input\\mdes-customer-service.yaml]
        [--java-mapping <path to mdes_cs_api_schemas.generated.json>]
        [-o mdes_cs_divergence_report.json]
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'mc_divergence'))

from diff_openapi_all import load_spec, get_operation, flatten_schema
from diff_predig_vs_data import extract_request_schema

DEFAULT_CS_SPEC_YAML = os.environ.get(
    'MDES_CS_SPEC_YAML', r'C:\Users\moham\Desktop\input\mdes-customer-service.yaml')
DEFAULT_CS_JAVA_MAPPING_JSON = os.environ.get(
    'MDES_CS_MAPPING_JSON',
    r'C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\generated\mdes_cs_api_schemas.generated.json')
DEFAULT_OUTPUT = os.path.join(HERE, 'mdes_cs_divergence_report.json')
DEFAULT_OUTPUT_MD = os.path.join(HERE, 'mdes_cs_divergence_report.md')

OPERATIONS = [
    ('Search', '/{id}/search'),
    ('Token Activate', '/{id}/token/activate'),
    ('Token Update', '/{id}/token/update'),
    ('Token Suspend', '/{id}/token/suspend'),
    ('Token Unsuspend', '/{id}/token/unsuspend'),
    ('Token Delete', '/{id}/token/delete'),
]

SPELLING_FOLDS = {
    'organisation': 'organization',
}


def normalize_leaf(name):
    n = re.sub(r'[^a-z0-9]', '', name.lower())
    return SPELLING_FOLDS.get(n, n)


def strip_wrapper_prefix(fields):
    """flatten_schema() includes the single top-level wrapper key (e.g.
    'SearchRequest') as its own '.'-free entry, with every real field
    nested under 'SearchRequest.'; the Java-side field paths don't carry
    this wrapper. Strip it so both sides line up."""
    tops = [k for k in fields if '.' not in k]
    if len(tops) != 1:
        return dict(fields)
    prefix = tops[0] + '.'
    return {k[len(prefix):]: v for k, v in fields.items() if k.startswith(prefix)}


def flatten_java_fields(fields, prefix=''):
    """The generated mapping nests object-typed fields under their own
    'properties' dict (e.g. AuditInfo -> properties -> UserId/UserName/...)
    rather than using dotted keys directly. Flatten to the same
    'Parent.Child' convention flatten_schema() uses on the spec side, so
    both sides compare on equal footing."""
    out = {}
    for name, info in fields.items():
        full = f'{prefix}{name}'
        out[full] = {
            'type': info.get('type'),
            'source': info.get('source'),
            'javaSource': info.get('javaSource'),
            'javaExpr': info.get('javaExpr'),
        }
        if info.get('properties'):
            out.update(flatten_java_fields(info['properties'], prefix=full + '.'))
    return out


def load_java_fields(mapping_json_path):
    """{operation_name: {field_path: [{'variant', 'source', 'javaSource'}]}}
    — a field can appear in multiple variants (e.g. Search's 3 request
    shapes), each independently tagged mechanical-scan/llm-inferred/unresolved."""
    with open(mapping_json_path, encoding='utf-8') as f:
        raw = json.load(f)
    out = {}
    for op in raw.get('operations', []):
        by_field = {}
        for variant_name, variant in op.get('variants', {}).items():
            flat = flatten_java_fields(variant.get('fields', {}))
            for field_path, info in flat.items():
                by_field.setdefault(field_path, []).append({
                    'variant': variant_name,
                    'source': info.get('source'),
                    'javaSource': info.get('javaSource'),
                })
        out[op['operation']] = by_field
    return out, raw.get('_meta', {})


def match_field(spec_path, java_fields_by_path):
    if spec_path in java_fields_by_path:
        return spec_path, java_fields_by_path[spec_path]
    spec_leaf = normalize_leaf(spec_path.split('.')[-1])
    for jpath, hits in java_fields_by_path.items():
        if normalize_leaf(jpath.split('.')[-1]) == spec_leaf:
            return jpath, hits
    return None, None


def audit_operation(spec_fields, java_fields_by_path):
    results = []
    for spec_path, info in sorted(spec_fields.items()):
        matched_path, hits = match_field(spec_path, java_fields_by_path)
        if hits is None:
            status = 'non_implemente'
        elif any(h['source'] == 'unresolved' for h in hits):
            status = 'non_verifiable'
        elif any(h['source'] == 'llm-inferred' for h in hits):
            status = 'partiel'
        else:
            status = 'implemente'
        results.append({
            'field': spec_path,
            'status': status,
            'required': info.get('required'),
            'type': info.get('type'),
            'matched_java_field': matched_path,
            'variants': sorted({h['variant'] for h in hits}) if hits else [],
            'java_source': sorted({h['javaSource'] for h in hits if h.get('javaSource')}) if hits else [],
        })
    return results


def run(spec_path, java_mapping_path):
    spec = load_spec(spec_path, repair=True)
    java_fields_by_op, java_meta = load_java_fields(java_mapping_path)

    operations = []
    for name, path in OPERATIONS:
        op = get_operation(spec, path, 'post')
        if op is None:
            operations.append({'operation': name, 'path': path, 'error': 'path absent du spec officiel'})
            continue
        schema, _ = extract_request_schema(op, spec)
        spec_fields = strip_wrapper_prefix(flatten_schema(schema))
        java_fields_by_path = java_fields_by_op.get(name, {})
        fields = audit_operation(spec_fields, java_fields_by_path)

        counts = {}
        for f in fields:
            counts[f['status']] = counts.get(f['status'], 0) + 1

        operations.append({
            'operation': name,
            'path': path,
            'total_fields': len(fields),
            'counts': counts,
            'fields': fields,
        })

    return {
        'spec_source': spec_path,
        'java_mapping_source': java_mapping_path,
        'java_mapping_generated_at': java_meta.get('generatedAt'),
        'operations': operations,
    }


def render_markdown(report):
    lines = [
        '# MDES Customer Service — écarts spec officiel vs implémentation Java (auto-généré)',
        '',
        f"Spec officiel : `{report['spec_source']}`",
        f"Extraction Java : `{report['java_mapping_source']}` (générée le {report['java_mapping_generated_at']})",
        '',
        '`non_implemente` = champ du spec absent de tout ce que le code Java construit actuellement. '
        '`non_verifiable` = un champ Java correspondant existe mais son identité n\'a pas pu être résolue '
        '(voir MDES_CS_API_JAVA_MAPPING_LINK.md) — écart dans la donnée, pas une absence confirmée. '
        '`partiel` = résolu par le modèle local plutôt que par un scan direct. `implemente` = trouvé directement.',
        '',
    ]
    for op in report['operations']:
        if 'error' in op:
            lines.append(f"## {op['operation']} — {op['path']}\n\n{op['error']}\n")
            continue
        c = op['counts']
        lines.append(f"## {op['operation']} — `POST {op['path']}`")
        lines.append(
            f"{op['total_fields']} champ(s) au total — "
            f"{c.get('implemente', 0)} implémenté(s), {c.get('partiel', 0)} partiel(s), "
            f"{c.get('non_verifiable', 0)} non vérifiable(s), {c.get('non_implemente', 0)} non implémenté(s)."
        )
        problems = [f for f in op['fields'] if f['status'] != 'implemente']
        if problems:
            lines.append('')
            lines.append('| Champ (spec officiel) | Statut | Requis | Champ Java correspondant |')
            lines.append('|---|---|---|---|')
            for f in problems:
                lines.append(
                    f"| `{f['field']}` | {f['status']} | {'oui' if f['required'] else 'non'} | "
                    f"{f['matched_java_field'] or '—'} |"
                )
        lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Compare le spec officiel MDES Customer Service a ce que le code Java construit.'
    )
    parser.add_argument('--spec', default=DEFAULT_CS_SPEC_YAML)
    parser.add_argument('--java-mapping', default=DEFAULT_CS_JAVA_MAPPING_JSON)
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--output-md', default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    if not os.path.exists(args.spec):
        print(f"ERROR: spec introuvable: {args.spec}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.java_mapping):
        print(f"ERROR: mapping Java introuvable: {args.java_mapping}", file=sys.stderr)
        sys.exit(1)

    report = run(args.spec, args.java_mapping)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(args.output_md, 'w', encoding='utf-8') as f:
        f.write(render_markdown(report))

    for op in report['operations']:
        if 'error' in op:
            print(f"  [FAIL] {op['operation']}: {op['error']}", file=sys.stderr)
            continue
        c = op['counts']
        print(f"  [ok] {op['operation']}: {op['total_fields']} champ(s) — "
              f"{c.get('non_implemente', 0)} non_implemente, {c.get('non_verifiable', 0)} non_verifiable, "
              f"{c.get('partiel', 0)} partiel", file=sys.stderr)

    print(f"[report] {args.output}", file=sys.stderr)
    print(f"[report] {args.output_md}", file=sys.stderr)


if __name__ == '__main__':
    main()
