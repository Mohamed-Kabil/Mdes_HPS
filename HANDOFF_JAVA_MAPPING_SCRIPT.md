# Handoff — building a Java-source-to-API mapping/audit script

> **STATUS: done for the MDES CS API set** — see `MDES_CS_API_JAVA_MAPPING_LINK.md`
> in this repo for the generated output and where the script actually lives
> (in the `pwc-api-sp5_api` checkout, not here). This doc is kept below for
> the original request/rationale and as a pattern reference for building an
> equivalent script for a different API domain.

This doc is written for a *different* Claude Code instance, working on a
different set of APIs, that has no prior context on this project
(`MDES_Project`). It explains the process/pattern already established here
so an equivalent script can be built for another API domain, following the
same conventions. It assumes you'll place your own Java source files and
your own script; nothing here is MDES-specific except the worked example.

## 1. The two distinct things this repo does — you only need pattern #2

This repo has two separate, unconnected pieces of work. Don't conflate them:

**(a) Automated OpenAPI spec diffing** (`mc_divergence/`, `diff_predig_vs_data.py`,
`check_field_changes.py`) — compares two *YAML/OpenAPI specs* against each
other (Mastercard's published spec vs. the internal implementation spec) to
find field-level divergences. This is YAML-vs-YAML. **Not the relevant
precedent for a Java-based script** — mentioned only so you don't mix it up
if you see it referenced elsewhere in this repo.

**(b) Manual API-to-Java-implementation mapping** (`java_mdes/*.java` +
`mdes_api_to_java_mapping.md`) — **this is the relevant precedent.** It
documents, per API endpoint, which Java file/method/branch actually
implements it. This is the pattern to turn into a script for your API set.

## 2. What the manual mapping precedent looks like

`mdes_api_to_java_mapping.md` is a hand-built table, one row per API
endpoint:

```
| MDES API (Mastercard) | Path | Java file | Entry point / branch |
|---|---|---|---|
| Search | POST /{id}/search | TokenInquiryRequestWebService.java | tokenInquiryRequest_35() -> execute(), network-code "02" branch (lines 147-169); variant selected by mapToRequestSearchByTUR() (566-588), ... |
| Token Activate | POST /{id}/token/activate | TokenLifeCycleItspWebService.java | tokenLifeCycleItsp_35() -> execute(), switch(request.getAction()) case "ACTIVATE" (144-147) -> mapToRequestActivate() (431-453) |
```

Plus a second table for things found in the same files that are **out of
scope** for the API set being mapped (e.g. branches handling a different
card network entirely) — worth keeping as a separate section so scope stays
explicit and nothing gets silently conflated.

This was built by reading the Java source and the API spec side by side and
recording: which class, which method, which conditional branch (with line
numbers so it stays traceable), handles each endpoint. It was **manual**,
not scripted, in this repo — your job is effectively to make an equivalent
of this table generation more automatic/repeatable.

## 3. Suggested shape for the script

Mirror the conventions already used in this repo's automated scripts
(`check_field_changes.py`, `phase1_historical_audit.py`):

- **Parse the Java source** to extract, per web-service class: method
  signatures, `switch`/`if` branches that dispatch on an action/request-type
  field, and the mapper methods they call (e.g. `mapToRequestXxx()`). Java
  isn't YAML, so this will be closer to a regex/AST-lite scan for method
  boundaries and branch conditions than a real parser — that's fine, this
  repo's own YAML "engine" (`diff_openapi_all.py`) is also a pragmatic
  heuristic tool, not a full spec-compliant parser, and it says so in its
  own docstring. Optimize for traceability (keep line numbers in the
  output) over completeness.
- **Compare against your API spec** (whatever defines your endpoints — an
  OpenAPI file, a Postman collection, hand-written docs) the same way
  `check_field_changes.py` compares note-derived fields against a spec: by
  endpoint/action name, normalized (lowercase, strip punctuation) since
  Java branch string literals and spec endpoint names won't match
  character-for-character.
- **Output**: a Markdown table identical in spirit to
  `mdes_api_to_java_mapping.md` (endpoint | path | Java file | entry point
  with line numbers), plus a JSON version if you want it machine-readable
  for a dashboard later — see `field_changes_report.json` /
  `predig_vs_data_report.json` in this repo for that pattern (flat list of
  dicts, one per finding, with `status`/`reliable` fields so a human can
  filter or trust it accordingly).
- **CLI shape**: argparse with defaults pointing at your files, one arg per
  input source, an `-o`/`--output` for the report path. See any script in
  this repo's root for the exact style (e.g. `check_field_changes.py`'s
  `main()`).

## 4. The linking convention (how the Java source gets wired in)

This repo does **not** vendor large external source files into the project
folder — files that live in another system of record get referenced by an
absolute path (or URL, for anything fetched over HTTP), with an env var
override, rather than copied in. The precedent, just established in this
repo for `data.yaml`:

```python
DEFAULT_DATA_YAML = os.environ.get('DATA_YAML_PATH', r'C:\Users\moham\Desktop\input\data.yaml')
```

`data.yaml` itself lives in `C:\Users\moham\Desktop\input\data.yaml` — a
folder outside any project directory — specifically so it can later be
swapped for a URL-backed fetch (like `mc_divergence/fetch_mc_source.py`
already does for Mastercard's `pre-dig.yaml`, downloading it fresh on every
run instead of reading a static local copy) without touching call sites.

**Apply the same pattern to your Java source path**: don't copy the `.java`
files into this repo's tree. Define something like:

```python
DEFAULT_JAVA_SOURCE_DIR = os.environ.get('JAVA_SOURCE_DIR', r'C:\Users\moham\Desktop\input\<your-folder>')
```

The user will drop the actual Java files at that path (same as they did for
`data.yaml`) and place your finished script in this repo, pointing at that
external path — so the repo stays lightweight and the Java source stays
whatever it already is (one source of truth), the same way `data.yaml`
isn't duplicated between `API_TEST` and here anymore.

## 5. Practical notes carried over from this repo's experience

- **No requirements.txt existed originally** — if your script needs
  third-party packages beyond stdlib, list them explicitly; don't assume
  the environment has them.
- **Test the actual run path, not just imports.** A script in this repo
  recently shipped a bug (`TypeError: cannot use 'dict' as a set element`)
  that only surfaced when the full pipeline ran end-to-end through the
  Flask dashboard, not when just checking `--help`/imports resolve. If your
  script feeds a dashboard or any downstream consumer, exercise the real
  call path once, not just a syntax check.
- **Keep line numbers/traceability in the output.** The whole point of the
  manual mapping table is that someone can jump straight to the exact Java
  line. A script that loses that (e.g. reports "found in
  TokenLifeCycleItspWebService.java" with no line/method) is strictly less
  useful than the manual version it's replacing.
