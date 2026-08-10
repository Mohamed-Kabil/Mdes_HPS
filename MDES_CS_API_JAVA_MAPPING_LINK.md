# Link: MDES Customer Service API -> Java field mapping (generated)

The script requested in `HANDOFF_JAVA_MAPPING_SCRIPT.md` was built, but lives
in the `pwc-api-sp5_api` checkout itself, not in this repo — that's where
the Java source and the rest of the MDES CS API reference material
(`mdes-customer-service (5).yaml`, `mdes_cs_api_schemas.json`,
`mdes_cs_api_inbound_constraints.json`) already are. This repo gets the
generated output, not a second copy of the extraction logic.

## Generated files (regenerate by re-running the script at the source)

    C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\generated\mdes_api_to_java_mapping.generated.md
    C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\generated\mdes_cs_api_schemas.generated.json

Script: `C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\extract_java_field_mapping.py`
(run it there — `python extract_java_field_mapping.py` — to refresh both
files after a codebase change).

## Read this alongside the existing manual precedent

- `mdes_api_to_java_mapping.md` (this repo) — hand-curated, has prose the
  generator doesn't attempt to reproduce (why fields are mutually
  exclusive, encryption-variant notes, etc.).
- The generated `.md`/`.json` above — field-level, line-number-traceable,
  re-derivable from source on demand. Each field is tagged
  `mechanical-scan` (found directly by the regex/variable-tracking
  scanner), `llm-inferred` (variable identity was lost — e.g. a JSON
  serialize/encrypt/re-parse roundtrip — and a local model resolved it,
  cached by content hash), or `unresolved` (identity lost, no
  cached/model resolution available or trustworthy — a real gap, not a
  confirmed absence). See the script's own docstring for the exact
  mechanics.

## Écarts connus (gaps in the generated data itself)

As delivered (run of 2026-08-07T10:32:39, generated with `--no-llm`), 2
fields are `unresolved` rather than actually resolved — a gap in the data,
not a defect in the script:

| Endpoint | Java file | Field | Status | Why |
|---|---|---|---|---|
| Token Update (`POST /{id}/token/update`, variant `accountUpdate`) | `PanLifeCycleItspWebService.java:173` | `TokenUpdateRequest` | `unresolved` | Identity-tracing skipped (`--no-llm` run); the mechanical scanner loses this variable across a serialize/encrypt/re-parse roundtrip and needs LLM or manual resolution to recover its actual field shape |
| Token Update (same variant) | `PanLifeCycleItspWebService.java:181` | `AuditInfo` | `unresolved` | Same cause as above |

Every other field across all 6 operations resolved cleanly
(`mechanical-scan`). This gap is confined to Token Update, the endpoint
that carries account/PAN data — treat these 2 fields as **not yet
verified**, not as "absent," when using this mapping for anything
security- or compliance-relevant. Closing it requires re-running
`extract_java_field_mapping.py` **without** `--no-llm` (the local model,
`Qwen/Qwen2.5-Coder-3B-Instruct`, needs to actually resolve the two
breaks) or a manual code read of those two roundtrips, same as the
original hand-curated mapping did for the whole file before this script
existed.

## Scope

Same 6 operations as everywhere else in this project: Search, Token
Activate, Token Update, Token Suspend, Token Unsuspend, Token Delete.

## Now diffed against Mastercard's spec too — `mdes_cs_divergence_report.py`

This repo now also does the comparison the section above said it didn't:
`mdes_cs_divergence_report.py` (project root) diffs the official MDES CS
OpenAPI spec against this generated Java mapping — same relationship as
`pre-dig.yaml` vs `data.yaml` in `mc_divergence/`, applied to the CS API
domain. The spec (`mdes-customer-service.yaml`, fetched from
`developer.mastercard.com/mdes-customer-service/documentation/llms-full.txt`'s
`api_specification(s)` list) is linked the same way as `data.yaml` — lives
at `C:\Users\moham\Desktop\input\mdes-customer-service.yaml`, overridable
via `MDES_CS_SPEC_YAML`. Regenerate with `python mdes_cs_divergence_report.py`;
output is `mdes_cs_divergence_report.json`/`.md`. Wired into the dashboard
as `/api/mdes_cs_divergence`.

Per-field status: `non_implemente` (no matching Java field in any variant),
`non_verifiable` (matched, but that Java field is itself `unresolved` —
propagates the Token Update gap above), `partiel` (matched via
`llm-inferred`), `implemente` (matched directly).

**Verified, not a scanner artifact**: Search and Token Activate both show
the entire `EncryptedAccountInformation` envelope (`EncryptedKey`, `Iv`,
`tag`, `aad`, `OaepHashingAlgorithm`, `PublicKeyFingerprint`,
`algorithmCipherMode`) as `non_implemente`, even though `AccountPan` right
next to it matched fine for Search's PAN variant. An earlier version of
this doc guessed this was a scanner blind spot (a shared encryption
helper class the mechanical scanner doesn't trace into) — **that guess was
checked against the actual source and was wrong.**

Direct read of `mapToRequestSearchByPan()`
(`TokenInquiryRequestWebService.java:485-518`) shows the method building
only `EncryptedData.CurrentAccount.AccountPan` and never touching the
envelope fields:

```java
EncryptedAccountInformation encryptedAccountInformation = new EncryptedAccountInformation();
EncryptedData encryptedData = new EncryptedData();
CurrentAccount currentAccount = new CurrentAccount();
currentAccount.setAccountPan(request.getEncryptData().getPan());
encryptedData.setCurrentAccount(currentAccount);
encryptedAccountInformation.setEncryptedData(encryptedData);
```

A project-wide grep confirms the shared encryption utility that *does*
build these fields elsewhere (`ClientApiTools.java`, used by
`AuthorizeServiceWebService.java`, `GetAccountInformationWebService.java`,
etc.) is **never called** from `TokenInquiryRequestWebService.java` at
all — not merely untraced by the scanner, genuinely absent from the call
graph. This is corroborated by Mastercard's own docs: the CS API support
page states *"the encryption functionality for the Search API is
currently not available in the Sandbox environment."* Three independent
sources now agree: the divergence report, the Java source, and
Mastercard's documentation. Treat this as a **real, confirmed gap** —
Search/Token Activate payload encryption isn't wired up in this codebase
yet — not a false positive to relay back to the extraction script.

Everything else in the `non_implemente` list (pagination `PageInfo`,
`CommentId`, `TokenRequestorId`, `TokenStatusCodes`, alternate PAN-search
identifiers `FinancialAccountId`/`Token`/`VirtualCardNumber`, etc.) looks
like a genuine "this optional spec field is never populated by this
client" finding, not a scanner artifact — those are legitimately optional
per-endpoint and this Java client only ever uses a fixed subset.

## What this does NOT do (yet)

Pre-release notes for the CS API (announced-but-not-yet-live field changes,
the way `mc_divergence/phase2_job_a_new_release_alert.py` already does for
Pre-Digitization) — planned as a follow-up, not built yet.
