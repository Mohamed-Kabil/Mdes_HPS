#!/usr/bin/env python3
"""
diff_openapi_all.py — single-file API documentation divergence detector.

Compares two OR MORE specs (e.g. a doc export, a PDF-extracted doc spec, and
a sandbox-generated OpenAPI spec) pairwise across every field, matched by
path + method, and reports every structural and textual divergence: required
fields, type/format/constraint mismatches, missing/extra fields, status
codes, content types, and description drift — labeled by which source(s)
disagree.

Handles BOTH input shapes transparently, per source:
  1. A standard OpenAPI 3.x document with a top-level "paths" map
     (any number of endpoints, $ref pointers resolved recursively).
  2. A flat single-endpoint doc export (keys: path, method, operationId,
     summary, description, tags, requestBody, responses; schemas already
     resolved under "schema_resolved (<content-type>)" keys) — e.g. a
     per-endpoint Fluid Topics slice.

Also repairs a known systemic YAML corruption: the first item of a block
sequence sometimes loses its leading indentation while later items in the
same list keep theirs. Repair only runs if the raw parse fails, so it never
touches an already-valid file.

Usage:
    python3 diff_openapi_all.py doc=doc_spec.yaml sandbox=sandbox_spec.yaml [pdf=pdf_spec.yaml ...] [-o report.json]

    Labels ("doc=", "sandbox=", ...) are optional — a bare path infers its
    label from the filename. Two files minimum; any number above that works.
    If no files are given on the command line, INPUT_SPECS below is used —
    edit that list directly, or call run_comparison() from other code (e.g.
    a future drag-and-drop UI), to wire up sources without touching argparse.

Flags:
    -o / --output FILE     write JSON report here (default: DEFAULT_OUTPUT_REPORT
                            below). Any previous file at that path is deleted
                            before the new report is written — always the
                            latest run's results, never a stale mix.
    --no-repair            never attempt the indentation-repair pass
    --no-descriptions      skip description comparison (pure structural diff)
    --normalize-only FILE  just load+repair+normalize FILE, dump it, and exit
                           (replaces the old standalone normalize_yaml.py)
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
# 0. Input sources — edit this list directly for ad-hoc runs, or leave it
#    empty/stale and pass files on the command line instead. A future
#    drag-and-drop UI should build a `[(label, path), ...]` list from the
#    dropped files and call run_comparison(specs, output_path) directly,
#    bypassing argparse entirely.
# ============================================================================

INPUT_SPECS = [
    ('doc', 'createcreditcard_v3.yaml'),      # Fluid Topics doc export (master)
    ('pdf_doc', 'data_from_pdf_v4.yaml'),     # doc spec extracted from the PDF
    ('sandbox', 'creditcardsand.yaml'),       # sandbox-generated OpenAPI spec
]

DEFAULT_OUTPUT_REPORT = 'divergence_report.json'


# ============================================================================
# 1. YAML repair (formerly yaml_utils.py)
# ============================================================================

BARE_KEY_RE = re.compile(r'^(\s*)(\S.*?):\s*$')
BARE_ITEM_RE = re.compile(r'^-(\s|$)')


def repair_first_list_item_indentation(text):
    """
    Fix a systemic corruption pattern: whenever a mapping key's value is a
    block sequence, the FIRST '-' item sometimes lost its leading
    indentation (dropped to column 0) while every subsequent item in the
    same list retains correct indentation. Detect 'key:' lines immediately
    followed by an under-indented '-' line and reindent that single line to
    key_indent + 2.
    """
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
    """Load a YAML file. If repair=True, only apply the indentation-repair
    pass when the raw text fails to parse as-is — never on an already-valid
    file (repairing a valid file can silently corrupt it)."""
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
# 2. Flat single-endpoint format detection + normalization
# ============================================================================

SCHEMA_RESOLVED_RE = re.compile(r'^schema_resolved \((.+)\)$')


def is_flat_endpoint_spec(spec):
    """True if `spec` is a flat single-endpoint doc export rather than a
    standard OpenAPI document (which has a top-level 'paths' map)."""
    return isinstance(spec, dict) and 'paths' not in spec and 'path' in spec and 'method' in spec


def _extract_content_dict(container):
    """Build an OpenAPI-style content dict {content_type: {'schema': ...}}
    from a flat requestBody/response entry by scanning for
    'schema_resolved (<content_type>)' keys."""
    content = {}
    if not isinstance(container, dict):
        return content
    for key, val in container.items():
        m = SCHEMA_RESOLVED_RE.match(key)
        if m:
            content[m.group(1)] = {'schema': val}
    return content


def normalize_flat_endpoint_spec(spec):
    """Convert a flat single-endpoint doc export into a standard
    {'paths': {path: {method: operation}}} structure so the rest of the
    pipeline can process either input shape transparently."""
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
    """Load a spec file and normalize it to the standard 'paths' structure,
    whether it's a full OpenAPI document or a flat single-endpoint export."""
    spec = load_yaml(path, repair=repair)
    if is_flat_endpoint_spec(spec):
        print(f"  [format] detected flat single-endpoint doc export in {path}, normalizing", file=sys.stderr)
        spec = normalize_flat_endpoint_spec(spec)
    return spec


# ============================================================================
# 3. $ref resolution
# ============================================================================

def resolve_refs(node, root, seen=None, depth=0):
    """Recursively resolve $ref pointers into inline structures.

    `depth` counts only actual $ref hops (how many pointers deep we've
    chased), not general tree recursion — a schema can be arbitrarily deep
    in properties/array-items/plain-list nesting (e.g. Card -> SubCard ->
    CardInfo -> Org -> ... -> KeyValue, several real-world docs go 10+
    levels without ever repeating a $ref) without that being circular.
    Counting ordinary tree depth here would eventually clobber unrelated
    leaf values (like the plain strings in a 'required' list) with the
    max-depth error sentinel once deep-but-legitimate nesting crossed the
    cap. `seen` still catches true cycles (a $ref reappearing in its own
    ancestor chain) immediately, before depth ever needs to matter."""
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
    """Collapse a path down to a bare, case/format-insensitive identity so
    the same endpoint can be matched across sources that spell it
    differently — e.g. doc/sandbox's '/CreateCreditCard/V3' and the
    PDF-extracted '/createCreditCard' both normalize to 'createcreditcard'.
    Drops version-like path segments (v1, v2, v3.5, ...) and all
    non-alphanumeric characters, then lowercases."""
    segments = [s for s in path.strip('/').split('/') if not VERSION_SEGMENT_RE.match(s)]
    return re.sub(r'[^a-z0-9]', '', ''.join(segments).lower())


def extract_request_schema(op, root):
    try:
        content = op['requestBody']['content']
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
    out = {}
    for status, resp in (op.get('responses') or {}).items():
        content = resp.get('content', {}) or {}
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
    """Strip HTML tags from a description so formatting differences
    (<p>text</p> vs text) aren't flagged as content differences."""
    if not text or not isinstance(text, str):
        return text
    if _HAS_BS4:
        return BeautifulSoup(text, 'html.parser').get_text(separator=' ').strip()
    # Fallback: naive tag stripping if bs4 isn't installed
    return re.sub(r'<[^>]+>', ' ', text).strip()


def _all_equal(values):
    """True if every value in the iterable is equal to the first (works for
    unhashable values like lists, unlike a set-based check)."""
    it = iter(values)
    try:
        first = next(it)
    except StopIteration:
        return True
    return all(v == first for v in it)


def describe_text_diff(field, texts):
    """Compare description strings across 2+ sources after stripping HTML.
    `texts` is {label: text}. Returns a divergence dict listing each source's
    cleaned text plus pairwise similarity ratios for the sources that
    disagree, or None if all sources agree."""
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
    minLength, pattern, enum, format}}"""
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
    every source where the field IS present."""
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
    """specs: {label: full_spec} for 2+ sources. `path_by_label` gives the
    (possibly differently-spelled) path each source actually uses for this
    endpoint — see normalize_path_key, which is what groups them together in
    the first place. A source absent from path_by_label (or whose path
    doesn't resolve to an operation) is flagged as missing but doesn't block
    comparing the rest, so a 3rd source's absence doesn't throw away the
    diff between the other two."""
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
        return result  # nothing left to compare structurally

    present_ops = {l: ops[l] for l in present_labels}

    # metadata drift (low severity)
    for meta in ['operationId', 'summary']:
        vals = {l: op.get(meta) for l, op in present_ops.items()}
        if not _all_equal(vals.values()):
            result['divergences'].append({'field': f'meta.{meta}', 'category': 'metadata_drift', 'values': vals})

    tag_vals = {l: sorted(set(op.get('tags', []) or [])) for l, op in present_ops.items()}
    if not _all_equal(tag_vals.values()):
        result['divergences'].append({'field': 'meta.tags', 'category': 'metadata_drift', 'values': tag_vals})

    # operation-level description
    if compare_descriptions:
        dd = describe_text_diff('meta.description', {l: op.get('description') for l, op in present_ops.items()})
        if dd:
            result['divergences'].append(dd)

    # request body
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
        rb_desc_vals = {l: (op.get('requestBody') or {}).get('description') for l, op in present_ops.items()}
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

    # responses
    resp_schemas = {l: extract_response_schemas(op, specs[l]) for l, op in present_ops.items()}

    codes_vals = {l: sorted(rs.keys()) for l, rs in resp_schemas.items()}
    if not _all_equal(codes_vals.values()):
        result['divergences'].append({'field': 'response.status_codes', 'category': 'status_code_mismatch',
                                       'values': codes_vals})

    common_codes = set.intersection(*(set(rs.keys()) for rs in resp_schemas.values()))

    for code in sorted(common_codes):
        if compare_descriptions:
            resp_desc_vals = {
                l: ((present_ops[l].get('responses') or {}).get(code, {}) or {}).get('description')
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
    """'label=path.yaml' -> (label, path); bare 'path.yaml' -> label inferred
    from the filename stem."""
    if '=' in arg:
        label, path = arg.split('=', 1)
        return label.strip(), path.strip()
    return os.path.splitext(os.path.basename(arg))[0], arg


def run_comparison(spec_entries, output_path, repair=True, compare_descriptions=True):
    """Entry point for anything other than the CLI (e.g. a future
    drag-and-drop UI): pass `[(label, path), ...]` for 2+ files and an
    output path, skip argparse entirely.

    Always erases whatever report previously existed at `output_path` before
    writing the new one, so the file on disk is always exactly this run's
    result — never a stale mix from an earlier comparison."""
    if len(spec_entries) < 2:
        raise ValueError("need at least two spec files to compare")

    specs = {}
    for label, path in spec_entries:
        print(f"  [load] '{label}' <- {path}", file=sys.stderr)
        specs[label] = load_spec(path, repair=repair)

    # Group by (normalized path, method) rather than raw path, so the same
    # endpoint spelled differently per source (e.g. doc's '/Foo/V3' vs a
    # PDF-extracted '/foo') still lands in one comparison instead of two
    # separate "missing in other sources" entries.
    groups = {}  # (norm_key, method) -> {label: raw_path}
    for label, spec in specs.items():
        for path, methods in (spec.get('paths') or {}).items():
            for method in methods:
                if method not in ('get', 'post', 'put', 'delete', 'patch'):
                    continue
                key = (normalize_path_key(path), method)
                groups.setdefault(key, {})[label] = path

    reports = [
        compare_endpoint(
            specs, path_by_label, method, compare_descriptions,
            display_path=path_by_label.get('doc', next(iter(path_by_label.values()))),
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
        description="Diff 2+ API specs (doc export, PDF-extracted doc, sandbox-generated OpenAPI, ...) "
                    "pairwise, matched by path+method, with $ref resolution and description comparison."
    )
    parser.add_argument('specs', nargs='*', metavar='[LABEL=]FILE',
                         help="2+ spec files, e.g. doc=doc.yaml sandbox=sb.yaml pdf=pdf.yaml. "
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
                         help="Just load+repair+normalize FILE, print it as clean YAML, and exit "
                              "(replaces the old standalone normalize_yaml.py)")
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
