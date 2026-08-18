# Integration notes — frontend_a_partager wired to real project data

This documents every decision, gap, and addition made while replacing the
old JS/JSON dashboard (`front_legacy/`, archived intact, not deleted) with
the `frontend_a_partager` template system, per `INTEGRATION.md` there.

## Structure

```
front/
  app.py              — Flask app: context processor, global routes, blueprint factory
  adapters/
    predig_adapter.py  — translates mc_divergence/phase1_historical_audit.py's
                          data into the template-facing {kpis, cards, ...} shape
    mdescs_adapter.py   — same, for mdes_cs_divergence_report.py + mdes_cs_prereleases.py
  notes_store.py        — new: JSON-backed per-endpoint notes
  env_store.py          — new: reads/writes mc_divergence/.env for Parametres
  data/                 — gitignored: notes_*.json, *_releases_cache.json (regenerable/local)
  templates/            — copied from frontend_a_partager, + networks/predig/, networks/mdescs/
  static/                — copied from frontend_a_partager, untouched
```

## Network mapping (your call, confirmed before building)

Two new networks, `predig` (MDES Pre-Digitization) and `mdescs` (MDES
Customer Service) — copied from the `mastercard` template family (both of
our parts have live refresh, unlike Visa's manual-only flow, so Mastercard's
shape fit both). Both use `logos/mastercard.svg` since both are Mastercard
products.

**Kept, not deleted, not wired**: `templates/networks/mastercard/` and
`templates/networks/visa/` (the original demo networks) are still on disk,
completely untouched. They're **not** in the active `NETWORKS` list in
`app.py`, so they don't appear in navigation and have no registered routes
— inventing fake Mastercard/Visa demo data for them would've been pure
busywork with no real value. If you ever want them live, they just need a
`NETWORKS` entry + a `build_network_blueprint()` call with a real adapter.

## Genuinely new features (this frontend expects them; the old dashboard didn't have them)

- **Historique page** — the source template only had a "coming soon" stub
  for this (`networks/_coming_soon.html`). Built a real one
  (`templates/networks/_historique.html` + `historique_view`/`historique_download`
  routes) reusing the existing `mc_divergence/reports/` listing, filtered by
  filename prefix so each network only shows its own reports.
- **Notes** — free-form per-endpoint comments. The project had zero
  persistence for this before. New `front/notes_store.py`, one JSON file per
  network (`front/data/notes_predig.json` / `notes_mdescs.json`).
- **Parametres (SMTP settings via web form)** — new `front/env_store.py`
  reads/writes `mc_divergence/.env` directly, preserving comments/layout,
  only rewriting the matched `KEY=` lines. Password field only overwrites
  the saved one if you actually type something (matches the template's own
  "leave blank to keep existing" copy).

## Simplifications / things to know before trusting this at face value

- **Part 2's "Actualiser" doesn't re-fetch from Mastercard.** Part 1 has a
  real fetcher (`fetch_mc_source.fetch_pre_dig_spec()`) that pulls a fresh
  `pre-dig.yaml` on refresh. Part 2's official spec
  (`mdes-customer-service.yaml`) has no equivalent auto-fetch script — it
  was fetched once by hand into `C:\Users\moham\Desktop\input\`. Clicking
  "Actualiser l'analyse" on the Comparaison/Releases pages for MDES Customer
  Service just recomputes from whatever's already on disk. Not a bug, just
  nothing to refresh yet.
- **The checkpoint-based alert mechanism isn't wired into this frontend.**
  The old dashboard had two distinct buttons per part — "Vérifier après le
  dernier audit" (advances a persisted checkpoint) and "Vérifier la
  dernière release" (releases newer than the checkpoint, never advances it)
  — for a "notify me only about what's NEW since I last looked" workflow.
  This template's Releases page has only one concept (a full sweep + a
  single "Actualiser" link), so I mapped it to the **comprehensive
  view** instead: every release ever found mentioning a tracked
  endpoint/operation, not just what's new. The underlying checkpoint
  functions (`phase2_job_a_new_release_alert.check_pending_since_predig()`,
  `mdes_cs_prereleases.check_pending()`, etc.) still exist and work — they're
  just not called from `front/app.py`. Say the word if you want that
  distinction back in this UI (e.g. as a second link on the Releases page).
- ~~Comparison-view email (both parts) reuses the Releases xlsx as its
  attachment~~ — **fixed**. `predig_adapter.export_comparison_xlsx()` now
  calls `phase1_historical_audit.render_report_xlsx([], ...)` (empty
  `audited_notes`, so it skips the notes-detail sheet and just writes
  Résumé + per-API + shared-fixes) to build its own dedicated
  `phase1_comparison_report.xlsx`, independent of Releases. Both parts now
  behave identically: Comparaison and Releases each have their own xlsx,
  and each email view is fully self-contained (doesn't require the other
  section to have been run first, doesn't go stale when only the other
  section is refreshed).
- **Email preview is plain text wrapped in `<pre>`**, not real HTML
  formatting. The existing `render_email_draft()`/`render_email_body()`
  functions produce lightly-marked-up plain text (`###` headers, `-` lists),
  and adding a markdown-to-HTML dependency just for this preview felt like
  overkill — flag if you'd rather have it rendered properly.
- **Severity mapping (Critique/Important/Mineur)** is a new concept this
  frontend introduces; the underlying data uses different vocabularies per
  part:
  - Part 1: `reliable=False` → Mineur; `reliable=True` + `non_implemente` →
    Critique; `reliable=True` + `partiel` → Important.
  - Part 2: `non_implemente` → Critique; `non_verifiable` → Important;
    `partiel` → Mineur.
  These are my judgment calls, not something either script defined —
  worth a second look if severity is going to drive real prioritization.

## Everything else

Comparaison, Releases (detail pages, filters, Excel export), Email
(two-step confirm, subject/intro/recipients editable), Configuration
(read-only endpoint list) all map cleanly onto existing pipeline functions
with no gaps — verified end-to-end via curl and in-browser (screenshots
taken during this session) for both networks.
