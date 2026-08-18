"""
predig_adapter.py — translates mc_divergence/phase1_historical_audit.py's
data shapes into the {kpis, cards, missing_fields, ...} shapes the
frontend_a_partager templates expect (see ../../frontend_a_partager/INTEGRATION.md
section 2). Keeps the template-facing shape in one place instead of scattering
it across view functions.

"Comparaison" = direct pre-dig.yaml vs data.yaml diff on the 7 priority
endpoints (audit_predig_vs_data_direct) — cheap, recomputed on every request
from whatever's already cached locally; "refresh" only re-fetches
pre-dig.yaml, the compute itself never touches the network.

"Releases" = the full note-based historical audit (phase1_historical_audit.run(),
cutoff 2025-01) — expensive (fetches/parses every release note since cutoff),
so its result is cached to disk and only recomputed when refresh is requested.

Comparaison and Releases each have their own dedicated Excel export/email
attachment (export_comparison_xlsx() / export_releases_xlsx()) — they used
to share one (Comparaison reusing the Releases xlsx), which meant a
Comparaison-view email was unavailable until Releases had been run at
least once, and went stale the moment Comparaison alone was refreshed.
Fixed so both views are fully independent of each other, matching how
mdescs_adapter.py already worked for MDES Customer Service.
"""

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(FRONT_DIR)
MC_DIVERGENCE_DIR = os.path.join(PROJECT_ROOT, "mc_divergence")
sys.path.insert(0, MC_DIVERGENCE_DIR)

import fetch_mc_source
import phase1_historical_audit as p1
import send_email as send_email_module
from .release_dates import best_date_iso, display_url

DATA_DIR = os.path.join(FRONT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RELEASES_CACHE_PATH = os.path.join(DATA_DIR, "predig_releases_cache.json")
COMPARISON_XLSX_PATH = os.path.join(MC_DIVERGENCE_DIR, "reports", "phase1_comparison_report.xlsx")

CACHE_DIR = fetch_mc_source.DEFAULT_CACHE_DIR
PREDIG_PATH = os.path.join(CACHE_DIR, "pre-dig.yaml")
PREDIG_META_PATH = os.path.join(CACHE_DIR, "pre-dig.yaml.meta.json")

ENDPOINT_DESCRIPTIONS = {
    '/requestActivationMethods': "Retourne les méthodes d'activation disponibles pour un token (SMS, email, etc.) avant sa première activation.",
    '/deliverActivationCode': "Envoie le code d'activation à l'utilisateur via la méthode choisie.",
    '/authorizeService': "Autorise/valide une transaction de tokenisation — coeur du flux d'enrôlement.",
    '/notifyServiceActivated': "Notifie que le service de tokenisation a été activé pour un compte.",
    '/notifyTokenUpdated': "Notifie qu'un token existant a été mis à jour (changement de PAN, expiration, etc.).",
    '/validateActivationCode': "Valide le code d'activation saisi par l'utilisateur.",
    '/getAccountInformation': "Retourne les informations du compte associé à un token.",
}


def _severity(status, reliable):
    if not reliable:
        return "Mineur"
    if status == "non_implemente":
        return "Critique"
    if status == "partiel":
        return "Important"
    return None


def _card_from_entry(path, display, entry):
    ep_name = path.lstrip('/')
    if not entry.get("endpoint_exists_in_predig"):
        return {
            "ep_name": ep_name, "path": path, "implemented": False,
            "error": "Endpoint absent de pre-dig.yaml (spec Mastercard).",
            "missing_count": 0, "missing_fields": [], "severity_counts": {},
            "severity_class": "na",
        }
    if not entry["endpoint_exists_in_data"]:
        return {
            "ep_name": ep_name, "path": path, "implemented": False, "error": None,
            "missing_count": len(entry["fields"]), "missing_fields": [], "severity_counts": {},
            "severity_class": "critique",
        }

    missing_fields = []
    severity_counts = {"Critique": 0, "Important": 0, "Mineur": 0}
    for f in entry["fields"]:
        sev = _severity(f["status"], f["reliable"])
        if sev is None:
            continue
        severity_counts[sev] += 1
        missing_fields.append({
            "field": f["name"], "severity": sev,
            "description": "; ".join(f.get("reasons") or []) or None,
        })

    if severity_counts["Critique"]:
        severity_class = "critique"
    elif severity_counts["Important"]:
        severity_class = "important"
    elif severity_counts["Mineur"]:
        severity_class = "mineur"
    else:
        severity_class = "conforme"

    return {
        "ep_name": ep_name, "path": path, "implemented": True, "error": None,
        "missing_count": len(missing_fields), "missing_fields": missing_fields,
        "severity_counts": severity_counts, "severity_class": severity_class,
    }


def _generated_at():
    if not os.path.exists(PREDIG_META_PATH):
        return None
    with open(PREDIG_META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    try:
        dt = datetime.fromisoformat(meta["fetched_at"])
        return dt.strftime("%d/%m/%Y %H:%M")
    except (KeyError, ValueError):
        return meta.get("fetched_at")


COMPARISON_CACHE_PATH = os.path.join(DATA_DIR, "predig_comparison_cache.json")


def _load_comparison_cache():
    if not os.path.exists(COMPARISON_CACHE_PATH):
        return None
    with open(COMPARISON_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_comparison_cache(payload):
    with open(COMPARISON_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _compute_comparison():
    """The actual compute is NOT cheap despite the direct diff itself being
    fast (~0.1s, see audit_predig_vs_data_direct) -- data.yaml is a 2.4MB
    file with thousands of corrupted list-item indentations that
    load_spec(repair=True) has to fix with a regex pass on every parse,
    which alone takes several seconds. Recomputing this on every page view
    (as an earlier version of this adapter did, reasoning the diff itself
    was cheap) made the Comparaison page take 7-11s to load every time --
    cached here the same way get_releases()/_run_releases_audit() already
    cache the much heavier note-based audit."""
    data_spec = p1.load_spec(p1.DEFAULT_DATA_YAML, repair=True)
    predig_spec = p1.load_spec(PREDIG_PATH, repair=True)
    predig_direct = p1.audit_predig_vs_data_direct(predig_spec, data_spec)

    cards = [_card_from_entry(path, display, predig_direct[path]) for path, display in p1.PRIORITY_PATH_DISPLAY]

    total_missing = sum(c["missing_count"] for c in cards)
    n_critical_endpoints = sum(1 for c in cards if c["severity_counts"].get("Critique"))
    n_compliant = sum(1 for c in cards if c["severity_class"] == "conforme")

    field_clusters = p1.group_shared_schema_fixes(predig_direct)
    shared_fixes = [{
        "title": target["data_origin"],
        "field_count": target["field_count"],
        "endpoint_count": target["endpoint_count"],
        "endpoints": target["endpoints"],
        "fields": sorted({f["name"] for p in p1.summarize_schema_fix_clusters(field_clusters)
                           if p["data_origin"] == target["data_origin"] for f in p["fields"]}),
    } for target in p1.summarize_by_data_target(field_clusters)]

    payload = {
        "generated_at": _generated_at(),
        "shared_fixes": shared_fixes,
        "kpis": {
            "total_missing": total_missing, "n_critical_endpoints": n_critical_endpoints,
            "n_compliant": n_compliant, "n_total": len(cards),
        },
        "cards": cards,
    }
    _save_comparison_cache(payload)
    return payload


def get_comparison(refresh=False):
    if refresh:
        fetch_mc_source.fetch_pre_dig_spec(CACHE_DIR)

    if not os.path.exists(PREDIG_PATH):
        return {"has_run": False}

    if refresh:
        return {"has_run": True, **_compute_comparison()}

    cached = _load_comparison_cache()
    if cached is None:
        return {"has_run": True, **_compute_comparison()}
    return {"has_run": True, **cached}


def get_comparison_detail(ep_name):
    data = get_comparison(refresh=False)
    if not data.get("has_run"):
        return None
    return next((c for c in data["cards"] if c["ep_name"] == ep_name), None)


def export_comparison_xlsx():
    """Dedicated comparison-only report — independent of the Releases xlsx
    (an earlier version of this function reused that one instead, which
    meant a comparison export/email was unavailable until Releases had
    been run at least once, and went stale the moment Comparaison alone
    was refreshed). render_report_xlsx() already builds a 'Résumé' +
    per-API + shared-fixes-sheet workbook and skips the notes-detail sheet
    when audited_notes is empty, so this needs no new writer, just calling
    it with audited_notes=[] and the direct diff freshly recomputed."""
    data_spec = p1.load_spec(p1.DEFAULT_DATA_YAML, repair=True)
    predig_spec = p1.load_spec(PREDIG_PATH, repair=True)
    predig_direct = p1.audit_predig_vs_data_direct(predig_spec, data_spec)
    p1.render_report_xlsx([], DEFAULT_CUTOFF, COMPARISON_XLSX_PATH, predig_direct)
    return COMPARISON_XLSX_PATH


def _load_releases_cache():
    if not os.path.exists(RELEASES_CACHE_PATH):
        return None
    with open(RELEASES_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_releases_cache(payload):
    with open(RELEASES_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


DEFAULT_CUTOFF = "2025-01"


def _run_releases_audit():
    cutoff = p1.parse_cutoff(DEFAULT_CUTOFF)
    audited_notes, subject, body = p1.run(
        p1.DEFAULT_DATA_YAML, cutoff, CACHE_DIR, p1.DEFAULT_REPORT_XLSX_PATH,
        refresh=True, send=False,
    )

    timeline = []
    for note in audited_notes:
        note_timeline = note.get("timeline") or {}
        for change in note["changes"]:
            # A change's endpoint_results can list endpoints outside the 7
            # priority APIs (audit_change() audits whatever the note
            # mentions, not just what this project tracks) -- the timeline
            # must only surface releases that actually touch a tracked
            # endpoint, otherwise it shows Mastercard changes to APIs we
            # don't implement at all.
            tracked_results = [er for er in change["endpoint_results"] if p1.is_priority_endpoint(er["endpoint"])]
            if not tracked_results:
                continue
            endpoints = sorted({er["endpoint"].lstrip('/') for er in tracked_results})
            fields = sorted({f["name"] for er in tracked_results for f in er.get("fields", [])})
            timeline.append({
                "title": change.get("title") or "(sans titre)",
                "mdes_release": note["mdes_release"],
                "description": change.get("description") or "",
                "mtf": note_timeline.get("mtf_date"),
                "production": note_timeline.get("production_date"),
                "published_date": note.get("published_date"),
                "date_sort": best_date_iso(note_timeline.get("production_date"),
                                            note_timeline.get("mtf_date"), note.get("published_date")),
                "url": display_url(note.get("url")),
                "endpoints": endpoints,
                "fields": fields,
            })
    timeline.sort(key=lambda t: t["date_sort"] or "", reverse=True)

    tracked_paths = [path.lstrip('/') for path, _ in p1.PRIORITY_PATH_DISPLAY]
    endpoints_with_releases = {ep for t in timeline for ep in t["endpoints"]}
    kpis = {
        "total_releases": len(timeline),
        "n_with_releases": len(endpoints_with_releases),
        "n_without_releases": len(tracked_paths) - len(endpoints_with_releases),
        "n_total": len(tracked_paths),
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M"),
        "kpis": kpis, "timeline": timeline,
        "xlsx_path": p1.DEFAULT_REPORT_XLSX_PATH, "subject": subject, "body": body,
    }
    _save_releases_cache(payload)
    return payload


def get_releases(refresh=False):
    if refresh:
        return {"has_run": True, **_run_releases_audit()}
    cached = _load_releases_cache()
    if cached is None:
        return {"has_run": False}
    return {"has_run": True, **cached}


def get_releases_timeline(refresh=False, date_from=None, date_to=None, endpoint=None):
    data = get_releases(refresh=refresh)
    if not data.get("has_run"):
        return data
    if "timeline" not in data:
        data = get_releases(refresh=True)
    items = data.get("timeline", [])
    if date_from:
        items = [t for t in items if t["date_sort"] and t["date_sort"] >= date_from]
    if date_to:
        items = [t for t in items if t["date_sort"] and t["date_sort"] <= date_to]
    if endpoint:
        items = [t for t in items if endpoint in t["endpoints"]]
    return {**data, "timeline": items}


def export_releases_xlsx():
    data = get_releases(refresh=False)
    if not data.get("has_run"):
        _run_releases_audit()
    return p1.DEFAULT_REPORT_XLSX_PATH


def get_email_data(view):
    if view == "releases":
        cached = _load_releases_cache()
        if cached is None:
            return {"has_data": False}
        return {
            "has_data": True, "subject": cached["subject"], "intro": cached["body"],
            "attachment_path": cached["xlsx_path"], "attachment_name": os.path.basename(cached["xlsx_path"]),
        }
    # view == "comparison" -- fully independent of Releases now: own xlsx,
    # own subject/intro, computed fresh from the current comparison state.
    comparison = get_comparison(refresh=False)
    if not comparison.get("has_run"):
        return {"has_data": False}
    subject = f"[MDES] Comparaison Pre-Digitization — {comparison['kpis']['total_missing']} écart(s)"
    intro_lines = [f"{comparison['kpis']['total_missing']} champ(s) manquant(s) sur {comparison['kpis']['n_total']} endpoint(s) prioritaires."]
    for c in comparison["cards"]:
        if c["missing_count"]:
            intro_lines.append(f"- {c['path']} : {c['missing_count']} champ(s) manquant(s)")
    xlsx_path = export_comparison_xlsx()
    return {
        "has_data": True, "subject": subject, "intro": "\n".join(intro_lines),
        "attachment_path": xlsx_path, "attachment_name": os.path.basename(xlsx_path),
    }


def send_report_email(view, subject, body, recipients):
    data = get_email_data(view)
    attachments = [data["attachment_path"]] if data.get("attachment_path") and os.path.exists(data["attachment_path"]) else None
    recipient_list = [r.strip() for r in recipients.split(",") if r.strip()] or None
    try:
        sent_to = send_email_module.send_email(subject, body, recipients=recipient_list, attachments=attachments)
        return "success", f"Email envoyé à {', '.join(sent_to)}."
    except send_email_module.SmtpConfigError as e:
        return "error", str(e)


def endpoints_config():
    return [{"name": path.lstrip('/'), "description": ENDPOINT_DESCRIPTIONS.get(path, display)}
            for path, display in p1.PRIORITY_PATH_DISPLAY]


def endpoint_names():
    return [path.lstrip('/') for path, _ in p1.PRIORITY_PATH_DISPLAY]
