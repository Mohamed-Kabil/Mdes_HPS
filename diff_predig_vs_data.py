#!/usr/bin/env python3
"""
diff_predig_vs_data.py — Mastercard "Pre-Digitization" pre-release spec vs.
current PowerCard/data.yaml divergence detector.

Same concept and engine as diff_openapi_all.py (field-by-field diff of two
OR MORE OpenAPI specs, matched by path + method, $ref-resolved, reporting
every missing field / type / enum / required / description divergence).

The one real-world wrinkle this script adds on top of diff_openapi_all.py:
pre-dig.yaml (the Mastercard pre-release note export) points requestBody and
each response entry at a *whole-object* $ref into components/requestBodies
and components/responses:

    requestBody:
      $ref: '#/components/requestBodies/RequestActivationMethodsRequest'
    responses:
      '200':
        $ref: '#/components/responses/RequestActivationMethodsResponse'

...whereas data.yaml (and diff_openapi_all.py's original targets) always
inline requestBody/response objects and only $ref at the schema level:

    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/AuthorizeServiceRq'

diff_openapi_all.py's extract_request_schema/extract_response_schemas index
straight into `op['requestBody']['content']` / `resp['content']`, so a
whole-object $ref (pre-dig.yaml's shape) would silently look like a missing
requestBody/response. The fix here: resolve_refs() the requestBody/response
container itself before reading '.content' out of it. resolve_refs() is a
no-op (structurally) on an already-inline container, so this works
transparently for both shapes and both file styles can be mixed freely.

Usage:
    python3 diff_predig_vs_data.py pre_dig=pre-dig.yaml data=data.yaml [-o report.json]

    Same flags as diff_openapi_all.py: -o/--output, --no-repair,
    --no-descriptions, --normalize-only FILE.
    If no files are given on the command line, INPUT_SPECS below is used.
"""

import argparse
import difflib
import json
import os
import re
import sys
from copy import deepcopy

import yaml

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


# ============================================================================
# 0a. Line-tracking YAML loader — lets every divergence in the report point
#     back at the exact source line in each original file, for manual review.
# ============================================================================

class LineDict(dict):
    """A plain dict that also remembers the 1-indexed source line of its
    opening key, stashed as an instance attribute (NOT a dict key) so it
    never shows up in .items()/.keys() iteration, property flattening, or
    equality checks — it rides along silently until flatten_schema reads it
    back out via getattr()."""


class LineLoader(yaml.SafeLoader):
    pass


def _construct_mapping_with_line(loader, node, deep=False):
    mapping = LineDict(yaml.SafeLoader.construct_mapping(loader, node, deep=deep))
    mapping.__line__ = node.start_mark.line + 1
    return mapping


LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_with_line
)


# ============================================================================
# 0. Input sources — edit directly for ad-hoc runs, or pass files on the CLI.
# ============================================================================

INPUT_SPECS = [
    ('pre_dig', r'C:\Users\moham\Downloads\pre-dig.yaml'),   # Mastercard Jan-2025 pre-release note export
    ('data', r'C:\Users\moham\Desktop\input\data.yaml'),  # current PowerCard Connect API spec
]

DEFAULT_OUTPUT_REPORT = 'predig_vs_data_report.json'


# ============================================================================
# 1. YAML repair (same systemic-corruption fixer as diff_openapi_all.py)
# ============================================================================

BARE_KEY_RE = re.compile(r'^(\s*)(\S.*?):\s*$')
BARE_ITEM_RE = re.compile(r'^-(\s|$)')


def repair_first_list_item_indentation(text):
    """Fix under-indented first '-' item of a block sequence (see
    diff_openapi_all.py for the full rationale). Only invoked when the raw
    parse fails, so a valid file is never touched."""
    lines = text.split('\n')
    fixes = 0
    for i in range(len(lines) - 1):
        m = BARE_KEY_RE.match(lines[i])
        if not m:
            continue
        key_indent = len(m.group(1))
        nxt = lines[i + 1]
        if BARE_ITEM_RE.match(nxt) and (len(nxt) - len(nxt.lstrip(' '))) < key_indent + 2:
            lines[i + 1] = (' ' * (key_indent + 2)) + nxt.lstrip(' ')
            fixes += 1
    return '\n'.join(lines), fixes


def load_yaml(path, repair=False, verbose=True):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    try:
        return yaml.load(text, Loader=LineLoader)
    except yaml.YAMLError:
        if not repair:
            raise
        repaired_text, n = repair_first_list_item_indentation(text)
        if verbose:
            print(f"  [repair] '{path}' failed to parse as-is; "
                  f"fixed {n} corrupted list-item indentation(s) and retrying", file=sys.stderr)
        return yaml.load(repaired_text, Loader=LineLoader)


# ============================================================================
# 2. Flat single-endpoint format detection + normalization (kept for parity;
#    neither pre-dig.yaml nor data.yaml currently uses this shape, but a
#    future 3rd source might).
# ============================================================================

SCHEMA_RESOLVED_RE = re.compile(r'^schema_resolved \((.+)\)$')


def is_flat_endpoint_spec(spec):
    return isinstance(spec, dict) and 'paths' not in spec and 'path' in spec and 'method' in spec


def _extract_content_dict(container):
    content = {}
    if not isinstance(container, dict):
        return content
    for key, val in container.items():
        m = SCHEMA_RESOLVED_RE.match(key)
        if m:
            content[m.group(1)] = {'schema': val}
    return content


def normalize_flat_endpoint_spec(spec):
    path = spec.get('path')
    method = (spec.get('method') or '').lower()

    operation = {
        'operationId': spec.get('operationId'),
        'summary': spec.get('summary'),
        'description': spec.get('description'),
        'tags': spec.get('tags', []) or [],
    }

    rb = spec.get('requestBody')
    if rb:
        operation['requestBody'] = {
            'description': rb.get('description'),
            'required': rb.get('required'),
            'content': _extract_content_dict(rb),
        }

    responses = {}
    for status, resp in (spec.get('responses') or {}).items():
        responses[str(status)] = {
            'description': (resp or {}).get('description'),
            'content': _extract_content_dict(resp or {}),
        }
    operation['responses'] = responses

    return {'paths': {path: {method: operation}}}


def load_spec(path, repair=False):
    spec = load_yaml(path, repair=repair)
    if is_flat_endpoint_spec(spec):
        print(f"  [format] detected flat single-endpoint doc export in {path}, normalizing", file=sys.stderr)
        spec = normalize_flat_endpoint_spec(spec)
    return spec


# ============================================================================
# 3. $ref resolution (identical engine to diff_openapi_all.py)
# ============================================================================

def resolve_refs(node, root, seen=None, depth=0):
    if seen is None:
        seen = set()

    if isinstance(node, dict):
        if '$ref' in node and isinstance(node['$ref'], str) and node['$ref'].startswith('#/'):
            if depth > 25:
                return {"__error__": "max depth exceeded (possible circular ref)"}
            ref_path = node['$ref'][2:].split('/')
            if node['$ref'] in seen:
                return {"__circular_ref__": node['$ref']}
            target = root
            try:
                for part in ref_path:
                    target = target[part]
            except (KeyError, TypeError):
                return {"__unresolved_ref__": node['$ref']}
            new_seen = seen | {node['$ref']}
            resolved = resolve_refs(target, root, new_seen, depth + 1)
            extra = {k: v for k, v in node.items() if k != '$ref'}
            if extra:
                merged = deepcopy(resolved) if isinstance(resolved, dict) else {}
                merged.update(resolve_refs(extra, root, seen, depth))
                return merged
            return resolved
        else:
            result = LineDict({k: resolve_refs(v, root, seen, depth) for k, v in node.items()})
            if hasattr(node, '__line__'):
                result.__line__ = node.__line__
            return result
    elif isinstance(node, list):
        return [resolve_refs(item, root, seen, depth) for item in node]
    else:
        return node


def get_operation(spec, path, method):
    paths = spec.get('paths', {})
    if path not in paths:
        return None
    return paths[path].get(method.lower())


VERSION_SEGMENT_RE = re.compile(r'^v\d+(\.\d+)*$', re.IGNORECASE)


def normalize_path_key(path):
    """Collapse a path to a bare, case/format-insensitive identity, e.g.
    data.yaml's '/authorizeService' and pre-dig.yaml's '/authorizeService'
    both normalize to 'authorizeservice' (also strips version segments like
    /V2, /V3.5 so differently-versioned paths still match)."""
    segments = [s for s in path.strip('/').split('/') if not VERSION_SEGMENT_RE.match(s)]
    return re.sub(r'[^a-z0-9]', '', ''.join(segments).lower())


def extract_request_schema(op, root):
    """Resolve the requestBody container itself first (handles pre-dig.yaml's
    whole-object $ref into components/requestBodies/*), THEN read '.content'
    out of it. A no-op for already-inline requestBody objects (data.yaml)."""
    rb = op.get('requestBody')
    if not rb:
        return None, []
    rb = resolve_refs(rb, root)
    try:
        content = rb['content']
    except (KeyError, TypeError):
        return None, []
    content_types = list(content.keys())
    schema_node = None
    if 'application/json' in content:
        schema_node = content['application/json'].get('schema')
    elif content_types:
        schema_node = content[content_types[0]].get('schema')
    resolved = resolve_refs(schema_node, root) if schema_node else None
    return resolved, content_types


def extract_response_schemas(op, root):
    """Same whole-object $ref resolution as extract_request_schema, applied
    per status code (handles pre-dig.yaml's '$ref: #/components/responses/*')."""
    out = {}
    for status, resp in (op.get('responses') or {}).items():
        resp = resolve_refs(resp, root) if resp else resp
        content = (resp or {}).get('content', {}) or {}
        schema_node = None
        if 'application/json' in content:
            schema_node = content['application/json'].get('schema')
        elif content:
            schema_node = list(content.values())[0].get('schema')
        out[status] = resolve_refs(schema_node, root) if schema_node else None
    return out


# ============================================================================
# 4. Description comparison (HTML stripping + similarity verdict)
# ============================================================================

def strip_html(text):
    if not text or not isinstance(text, str):
        return text
    if _HAS_BS4:
        return BeautifulSoup(text, 'html.parser').get_text(separator=' ').strip()
    return re.sub(r'<[^>]+>', ' ', text).strip()


def _all_equal(values):
    it = iter(values)
    try:
        first = next(it)
    except StopIteration:
        return True
    return all(v == first for v in it)


def describe_text_diff(field, texts):
    cleaned = {label: (strip_html(t) if t else t) for label, t in texts.items()}

    if _all_equal(cleaned.values()):
        return None

    labels = list(cleaned.keys())
    pairwise = {}
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = cleaned[labels[i]], cleaned[labels[j]]
            if a == b:
                continue
            sim = difflib.SequenceMatcher(None, a or "", b or "").ratio()
            pairwise[f'{labels[i]}~{labels[j]}'] = round(sim, 3)

    return {
        'field': field,
        'category': 'description_drift',
        'values': cleaned,
        'pairwise_similarity': pairwise,
    }


# ============================================================================
# 5. Schema flattening + structural diff
# ============================================================================

def flatten_schema(schema, prefix=""):
    """Flatten a resolved schema into {field_path: {type, required, maxLength,
    minLength, pattern, enum, format, description}}."""
    fields = {}
    if not isinstance(schema, dict):
        return fields
    required = set(schema.get('required', []) or [])
    props = schema.get('properties', {}) or {}
    for name, sub in props.items():
        full = f"{prefix}{name}"
        info = {
            'required': name in required,
            'type': sub.get('type'),
            'format': sub.get('format'),
            'maxLength': sub.get('maxLength'),
            'minLength': sub.get('minLength'),
            'pattern': sub.get('pattern'),
            'enum': sub.get('enum'),
            'description': sub.get('description'),
            'line': getattr(sub, '__line__', None),
        }
        fields[full] = info
        if sub.get('type') == 'object' or ('properties' in sub):
            fields.update(flatten_schema(sub, prefix=full + "."))
        elif sub.get('type') == 'array' and isinstance(sub.get('items'), dict) and 'properties' in sub['items']:
            fields.update(flatten_schema(sub['items'], prefix=full + "[]."))
    return fields


def diff_field_sets(field_dicts, compare_descriptions=True):
    """field_dicts: {label: {field_path: info}} for 2+ sources. Reports a
    field as missing wherever it's absent from at least one source (and
    present in at least one other), and diffs attrs/descriptions across
    every source where the field IS present. This is also where a new
    Mastercard enum value like EMV_3DS on activationMethod.type would show
    up as an `attr_mismatch:enum` (if both sides define an enum list) or
    simply never surface if neither side declares an enum at all — a
    freeform `type: string` field with no enum can silently accept (or
    silently fail to document) any value, which is worth flagging by eye
    even when the diff itself reports "no divergence"."""
    divergences = []
    all_keys = set()
    for fd in field_dicts.values():
        all_keys |= set(fd.keys())
    labels = list(field_dicts.keys())

    for key in sorted(all_keys):
        present = {label: field_dicts[label].get(key) for label in labels}
        missing = [label for label, v in present.items() if v is None]
        lines = {label: (v.get('line') if v else None) for label, v in present.items()}
        if missing:
            divergences.append({
                'field': key, 'category': 'field_missing_in',
                'values': {label: ('present' if v is not None else 'missing') for label, v in present.items()},
                'lines': lines,
            })
            continue

        for attr in ['required', 'type', 'format', 'maxLength', 'minLength', 'pattern', 'enum']:
            vals = {label: present[label].get(attr) for label in labels}
            if not _all_equal(vals.values()):
                divergences.append({'field': key, 'category': f'attr_mismatch:{attr}', 'values': vals, 'lines': lines})

        if compare_descriptions:
            dd = describe_text_diff(key, {label: present[label].get('description') for label in labels})
            if dd:
                dd['lines'] = lines
                divergences.append(dd)
    return divergences


def compare_endpoint(specs, path_by_label, method, compare_descriptions=True, display_path=None):
    ops = {
        label: get_operation(specs[label], path_by_label[label], method)
        for label in specs if label in path_by_label
    }
    result = {
        'path': display_path or next(iter(path_by_label.values())),
        'method': method.upper(),
        'source_paths': dict(path_by_label),
        'divergences': [],
    }

    present_labels = [l for l, op in ops.items() if op is not None]
    missing_labels = [l for l in specs if l not in present_labels]

    if missing_labels:
        result['divergences'].append({
            'field': '(endpoint)', 'category': 'endpoint_missing_in',
            'values': {l: ('present' if l in present_labels else 'missing') for l in specs},
        })

    if len(present_labels) < 2:
        return result

    present_ops = {l: ops[l] for l in present_labels}

    for meta in ['operationId', 'summary']:
        vals = {l: op.get(meta) for l, op in present_ops.items()}
        if not _all_equal(vals.values()):
            result['divergences'].append({'field': f'meta.{meta}', 'category': 'metadata_drift', 'values': vals})

    tag_vals = {l: sorted(set(op.get('tags', []) or [])) for l, op in present_ops.items()}
    if not _all_equal(tag_vals.values()):
        result['divergences'].append({'field': 'meta.tags', 'category': 'metadata_drift', 'values': tag_vals})

    if compare_descriptions:
        dd = describe_text_diff('meta.description', {l: op.get('description') for l, op in present_ops.items()})
        if dd:
            result['divergences'].append(dd)

    req_schemas, req_cts = {}, {}
    for l, op in present_ops.items():
        schema, cts = extract_request_schema(op, specs[l])
        req_schemas[l] = schema
        req_cts[l] = cts

    ct_vals = {l: sorted(cts) for l, cts in req_cts.items()}
    if not _all_equal(ct_vals.values()):
        result['divergences'].append({'field': 'request.content_types', 'category': 'content_type_mismatch',
                                       'values': ct_vals})

    if compare_descriptions:
        rb_desc_vals = {l: (resolve_refs(op.get('requestBody'), specs[l]) or {}).get('description')
                         for l, op in present_ops.items()}
        dd = describe_text_diff('request.description', rb_desc_vals)
        if dd:
            result['divergences'].append(dd)

    req_field_dicts = {l: (flatten_schema(s) if s else {}) for l, s in req_schemas.items()}
    for d in diff_field_sets(req_field_dicts, compare_descriptions):
        d['field'] = f"request.{d['field']}"
        result['divergences'].append(d)

    req_required_vals = {l: sorted((s or {}).get('required', []) or []) for l, s in req_schemas.items()}
    if not _all_equal(req_required_vals.values()):
        result['divergences'].append({
            'field': 'request.(top-level required set)', 'category': 'required_set_mismatch',
            'values': req_required_vals,
        })

    resp_schemas = {l: extract_response_schemas(op, specs[l]) for l, op in present_ops.items()}

    codes_vals = {l: sorted(rs.keys()) for l, rs in resp_schemas.items()}
    if not _all_equal(codes_vals.values()):
        result['divergences'].append({'field': 'response.status_codes', 'category': 'status_code_mismatch',
                                       'values': codes_vals})

    common_codes = set.intersection(*(set(rs.keys()) for rs in resp_schemas.values()))

    for code in sorted(common_codes):
        if compare_descriptions:
            resp_desc_vals = {
                l: (resolve_refs((present_ops[l].get('responses') or {}).get(code), specs[l]) or {}).get('description')
                for l in present_labels
            }
            dd = describe_text_diff(f'response[{code}].description', resp_desc_vals)
            if dd:
                result['divergences'].append(dd)

        resp_field_dicts = {
            l: (flatten_schema(resp_schemas[l][code]) if resp_schemas[l].get(code) else {})
            for l in present_labels
        }
        for d in diff_field_sets(resp_field_dicts, compare_descriptions):
            d['field'] = f"response[{code}].{d['field']}"
            result['divergences'].append(d)

        req_set_vals = {l: sorted((resp_schemas[l].get(code) or {}).get('required', []) or []) for l in present_labels}
        if not _all_equal(req_set_vals.values()):
            result['divergences'].append({
                'field': f'response[{code}].(top-level required set)', 'category': 'required_set_mismatch',
                'values': req_set_vals,
            })

    return result


# ============================================================================
# 6. CLI
# ============================================================================

def _parse_spec_arg(arg):
    if '=' in arg:
        label, path = arg.split('=', 1)
        return label.strip(), path.strip()
    return os.path.splitext(os.path.basename(arg))[0], arg


def run_comparison(spec_entries, output_path, repair=True, compare_descriptions=True):
    if len(spec_entries) < 2:
        raise ValueError("need at least two spec files to compare")

    specs = {}
    for label, path in spec_entries:
        print(f"  [load] '{label}' <- {path}", file=sys.stderr)
        specs[label] = load_spec(path, repair=repair)

    groups = {}  # (norm_key, method) -> {label: raw_path}
    for label, spec in specs.items():
        for path, methods in (spec.get('paths') or {}).items():
            for method in methods:
                if method not in ('get', 'post', 'put', 'delete', 'patch'):
                    continue
                key = (normalize_path_key(path), method)
                groups.setdefault(key, {})[label] = path

    primary_label = spec_entries[0][0]
    reports = [
        compare_endpoint(
            specs, path_by_label, method, compare_descriptions,
            display_path=path_by_label.get(primary_label, next(iter(path_by_label.values()))),
        )
        for (norm_key, method), path_by_label in sorted(groups.items())
    ]

    for r in reports:
        print(f"\n=== {r['method']} {r['path']} ===")
        if not r['divergences']:
            print("  No divergences found.")
            continue
        for d in r['divergences']:
            print(f"  [{d['category']}] {d['field']}")
            for label, v in d.get('values', {}).items():
                print(f"      {label}: {v}")
            if 'pairwise_similarity' in d and d['pairwise_similarity']:
                print(f"      similarity: {d['pairwise_similarity']}")

    total = sum(len(r['divergences']) for r in reports)
    print(f"\n--- TOTAL: {len(reports)} endpoint(s) checked across {len(specs)} source(s) "
          f"({', '.join(specs.keys())}), {total} divergence(s) found ---")

    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"  [output] erased previous report at {output_path}", file=sys.stderr)
    with open(output_path, 'w') as f:
        json.dump(reports, f, indent=2, default=str)
    print(f"\nFull report written to: {output_path}")

    return reports


def main():
    parser = argparse.ArgumentParser(
        description="Diff Mastercard pre-dig.yaml (pre-release note export) against data.yaml "
                    "(or any 2+ OpenAPI specs), matched by path+method, with $ref resolution "
                    "(including whole-object requestBody/response $refs) and description comparison."
    )
    parser.add_argument('specs', nargs='*', metavar='[LABEL=]FILE',
                         help="2+ spec files, e.g. pre_dig=pre-dig.yaml data=data.yaml. "
                              "Label is optional (inferred from the filename if omitted). "
                              "If omitted entirely, falls back to the INPUT_SPECS list defined "
                              "at the top of this file.")
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_REPORT,
                         help=f"Path to write the JSON report (default: {DEFAULT_OUTPUT_REPORT}). "
                              "Any existing file at this path is deleted before the new report is written.")
    parser.add_argument('--no-repair', action='store_true',
                         help="Never attempt the YAML indentation repair pass")
    parser.add_argument('--no-descriptions', action='store_true',
                         help="Skip description comparison (pure structural diff, less noise)")
    parser.add_argument('--normalize-only', metavar='FILE',
                         help="Just load+repair+normalize FILE, print it as clean YAML, and exit")
    args = parser.parse_args()

    if args.normalize_only:
        spec = load_spec(args.normalize_only, repair=not args.no_repair)
        print(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        return

    spec_entries = [_parse_spec_arg(a) for a in args.specs] if args.specs else INPUT_SPECS
    if len(spec_entries) < 2:
        parser.error("need at least two spec files to compare (pass them as args, "
                      "or populate INPUT_SPECS at the top of this file)")

    run_comparison(spec_entries, args.output, repair=not args.no_repair,
                   compare_descriptions=not args.no_descriptions)


if __name__ == '__main__':
    main()
