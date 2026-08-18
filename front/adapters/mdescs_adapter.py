"""
mdescs_adapter.py — same role as predig_adapter.py, for the MDES Customer
Service part (mdes_cs_divergence_report.py + mdes_cs_prereleases.py).

"Comparaison" = official CS spec vs Java extraction (mdes_cs_divergence_report.run()).
Both sides are static local files (no live network fetch step exists for
either today — see the summary note about this gap), so "refresh" here just
recomputes from whatever's on disk; it's cheap either way.

"Releases" = every CS pre-release note that mentions a tracked operation,
across the full release-history table (mdes_cs_prereleases.filter_relevant_releases()
over ALL entries, not the checkpoint-scoped subset the old dashboard's
"Vérifier après / Vérifier la dernière" buttons used — see summary note).
"""

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(FRONT_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "mc_divergence"))

import mdes_cs_divergence_report as cs_div
import mdes_cs_prereleases as cs_pre
import send_email as send_email_module
from .release_dates import best_date_iso, display_url

DATA_DIR = os.path.join(FRONT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
RELEASES_CACHE_PATH = os.path.join(DATA_DIR, "mdescs_releases_cache.json")

OPERATION_DESCRIPTIONS = {
    "Search": "Recherche un ou plusieurs tokens associés à un PAN, un TUR ou un device ID.",
    "Token Activate": "Active un token pour la première fois après provisioning.",
    "Token Update": "Met à jour les données associées à un ou plusieurs tokens (ex. FPAN).",
    "Token Suspend": "Change le statut d'un token de actif à suspendu.",
    "Token Unsuspend": "Change le statut d'un token de suspendu à actif.",
    "Token Delete": "Supprime définitivement un token.",
}


def _slug(operation_name):
    return operation_name.lower().replace(" ", "-")


def _severity(status):
    return {"non_implemente": "Critique", "non_verifiable": "Important", "partiel": "Mineur"}.get(status)


def _card_from_op(op):
    ep_name = _slug(op["operation"])
    if "error" in op:
        return {
            "ep_name": ep_name, "path": op["path"], "implemented": False, "error": op["error"],
            "missing_count": 0, "missing_fields": [], "severity_counts": {}, "severity_class": "na",
        }

    missing_fields = []
    severity_counts = {"Critique": 0, "Important": 0, "Mineur": 0}
    for f in op["fields"]:
        sev = _severity(f["status"])
        if sev is None:
            continue
        severity_counts[sev] += 1
        description = f"Champ Java correspondant : {f['matched_java_field']}" if f.get("matched_java_field") else None
        missing_fields.append({"field": f["field"], "severity": sev, "description": description})

    if severity_counts["Critique"]:
        severity_class = "critique"
    elif severity_counts["Important"]:
        severity_class = "important"
    elif severity_counts["Mineur"]:
        severity_class = "mineur"
    else:
        severity_class = "conforme"

    return {
        "ep_name": ep_name, "path": op["path"], "implemented": True, "error": None,
        "missing_count": len(missing_fields), "missing_fields": missing_fields,
        "severity_counts": severity_counts, "severity_class": severity_class,
    }


def get_comparison(refresh=False):
    if not os.path.exists(cs_div.DEFAULT_CS_SPEC_YAML) or not os.path.exists(cs_div.DEFAULT_CS_JAVA_MAPPING_JSON):
        return {"has_run": False}

    report = cs_div.run(cs_div.DEFAULT_CS_SPEC_YAML, cs_div.DEFAULT_CS_JAVA_MAPPING_JSON)
    cards = [_card_from_op(op) for op in report["operations"]]

    total_missing = sum(c["missing_count"] for c in cards)
    n_critical_endpoints = sum(1 for c in cards if c["severity_counts"].get("Critique"))
    n_compliant = sum(1 for c in cards if c["severity_class"] == "conforme")

    shared_fixes = [{
        "title": g["root_field"], "field_count": g["field_count"],
        "endpoint_count": g["operation_count"], "endpoints": g["operations"],
        "fields": g["fields"],
    } for g in (report.get("shared_gaps") or [])]

    return {
        "has_run": True,
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "kpis": {
            "total_missing": total_missing, "n_critical_endpoints": n_critical_endpoints,
            "n_compliant": n_compliant, "n_total": len(cards),
        },
        "cards": cards, "shared_fixes": shared_fixes,
        "_report": report,
    }


def get_comparison_detail(ep_name):
    data = get_comparison(refresh=False)
    if not data.get("has_run"):
        return None
    return next((c for c in data["cards"] if c["ep_name"] == ep_name), None)


def export_comparison_xlsx():
    data = get_comparison(refresh=False)
    if not data.get("has_run"):
        return None
    cs_div.render_report_xlsx(data["_report"], cs_div.DEFAULT_REPORT_XLSX_PATH)
    return cs_div.DEFAULT_REPORT_XLSX_PATH


def _load_releases_cache():
    if not os.path.exists(RELEASES_CACHE_PATH):
        return None
    with open(RELEASES_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_releases_cache(payload):
    with open(RELEASES_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _change_matched_apis(change):
    """Which of the 6 tracked CS ops a single change actually touches.
    Two independent signals, since notes are inconsistent about which one
    they use: cs_pre.find_matching_apis() keyword-matches the change's own
    prose (title/description) against display names ('Token Activate'), but
    a change's real endpoint list ('API Reference:' markers, e.g.
    'GET /{id}/token/activate') references REST path fragments instead --
    those never contain the display-name phrase, so path-matching against
    cs_div.OPERATIONS is needed too or such changes go undetected entirely
    (e.g. the March 2026 note's Change 1/3, whose only tracked-op signal is
    the endpoint list)."""
    text = " ".join(filter(None, [change.get("title"), change.get("description")]))
    matched = set(cs_pre.find_matching_apis(text))
    for ep_ref in change.get("endpoints") or []:
        for api_name, api_path in cs_div.OPERATIONS:
            if api_path in ep_ref:
                matched.add(api_name)
    return [api for api in cs_pre.TARGET_APIS if api in matched]


def _run_releases_check():
    entries = cs_pre.get_release_notes_table(cs_pre.DEFAULT_CACHE_DIR, refresh=True)
    relevant = cs_pre.filter_relevant_releases(entries, cs_pre.DEFAULT_CACHE_DIR)

    timeline = []
    for r in relevant:
        note_timeline = r["parsed"]["timeline"]
        for c in r["parsed"]["changes"]:
            # r["matched_apis"] is note-wide (find_matching_apis over the
            # WHOLE note text) -- a note can be "relevant" because one change
            # mentions a tracked op while an unrelated change sits right next
            # to it. Recompute per-change so an untracked change doesn't
            # inherit the note's tracked tag, mirroring predig_adapter.py's
            # per-change endpoint filter.
            change_apis = _change_matched_apis(c)
            if not change_apis:
                continue
            change_fields = [f["name"] for f in c.get("fields", [])]
            timeline.append({
                "title": c.get("title") or "(sans titre)",
                "mdes_release": r["title"],
                "description": c.get("description") or "",
                "mtf": note_timeline.get("mtf_date"),
                "production": note_timeline.get("production_date"),
                "published_date": r.get("upgrade_date"),
                "date_sort": best_date_iso(note_timeline.get("production_date"),
                                            note_timeline.get("mtf_date"), r.get("upgrade_date")),
                "url": display_url(r.get("url")),
                "endpoints": sorted({_slug(api) for api in change_apis}),
                "fields": change_fields,
            })
    timeline.sort(key=lambda t: t["date_sort"] or "", reverse=True)

    endpoints_with_releases = {ep for t in timeline for ep in t["endpoints"]}
    kpis = {
        "total_releases": len(timeline),
        "n_with_releases": len(endpoints_with_releases),
        "n_without_releases": len(cs_pre.TARGET_APIS) - len(endpoints_with_releases),
        "n_total": len(cs_pre.TARGET_APIS),
    }

    subject = cs_pre.email_subject(relevant) if relevant else "[MDES Customer Service] 0 new release(s) impacting tracked operations"
    body = cs_pre.render_email_body(relevant) if relevant else "Aucune release pertinente trouvée pour les opérations suivies."
    xlsx_path = cs_pre.default_report_xlsx_path()
    if relevant:
        cs_pre.render_report_xlsx(relevant, xlsx_path)

    payload = {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "kpis": kpis, "timeline": timeline,
        "xlsx_path": xlsx_path if relevant else None, "subject": subject, "body": body,
    }
    _save_releases_cache(payload)
    return payload


def get_releases(refresh=False):
    if refresh:
        return {"has_run": True, **_run_releases_check()}
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
    if not data.get("has_run") or not data.get("xlsx_path"):
        data = {"has_run": True, **_run_releases_check()}
    return data.get("xlsx_path")


def get_email_data(view):
    if view == "releases":
        cached = _load_releases_cache()
        if cached is None:
            return {"has_data": False}
        if not cached.get("xlsx_path"):
            return {"has_data": True, "subject": cached["subject"], "intro": cached["body"],
                    "attachment_path": None, "attachment_name": "(aucune release pertinente — pas de pièce jointe)"}
        return {
            "has_data": True, "subject": cached["subject"], "intro": cached["body"],
            "attachment_path": cached["xlsx_path"], "attachment_name": os.path.basename(cached["xlsx_path"]),
        }

    comparison = get_comparison(refresh=False)
    if not comparison.get("has_run"):
        return {"has_data": False}
    xlsx_path = export_comparison_xlsx()
    return {
        "has_data": True,
        "subject": cs_div.email_subject(comparison["_report"]),
        "intro": cs_div.render_email_body(comparison["_report"]),
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
    return [{"name": _slug(name), "description": f"{path} — {OPERATION_DESCRIPTIONS.get(name, name)}"}
            for name, path in cs_div.OPERATIONS]


def endpoint_names():
    return [_slug(name) for name, _ in cs_div.OPERATIONS]
