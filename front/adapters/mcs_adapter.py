"""
mcs_adapter.py — same role as predig_adapter.py, for Mastercard Checkout
Solutions (mc_divergence/mcs_divergence.py).

"Comparaison" = direct diff between the official Mastercard Checkout
Solutions specs (Card API + Cards Batch Enroll API, fetched fresh from
static.developer.mastercard.com) and data.yaml's 5 tracked "*OnC2P"
operations (EnrollCardOnC2P / GetDataFromC2P / DeleteDataOnC2P /
BulkEnrollmentOnC2P / GetC2PBatchResult) -- same relationship as predig's
Comparaison has to pre-dig.yaml vs data.yaml, just against two official spec
files instead of one. Cached the same way (recompute is cheap, but
data.yaml's repair pass on every load is not -- see predig_adapter.py's
_compute_comparison() docstring for why).

"Releases" is NOT implemented for this network: unlike MDES Pre-Digitization
and MDES Customer Service, there's no discovered release-notes index page for
Mastercard Checkout Solutions to fetch on a schedule, so get_releases_timeline()
always reports has_run=False rather than pretending an automated source
exists. The generic front/templates/networks/_releases_timeline.html already
renders that state ("No analysis run yet") without special-casing.
"""

import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(FRONT_DIR)
MC_DIVERGENCE_DIR = os.path.join(PROJECT_ROOT, "mc_divergence")
sys.path.insert(0, MC_DIVERGENCE_DIR)

import mcs_divergence as mcs
import phase1_historical_audit as p1
import send_email as send_email_module
from .report_naming import dated_report_path

DATA_DIR = os.path.join(FRONT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
REPORTS_DIR = os.path.join(MC_DIVERGENCE_DIR, "reports")
NETWORK_SLUG = "checkout_solutions"
COMPARISON_CACHE_PATH = os.path.join(DATA_DIR, "mcs_comparison_cache.json")

OPERATION_DESCRIPTIONS = {
    '/EnrollCardOnC2P/V2': "Enrolls a card into Mastercard Checkout Solutions, returning a srcDigitalCardId for later use.",
    '/GetDataFromC2P/V2': "Retrieves the latest masked card data for a previously enrolled card.",
    '/DeleteDataOnC2P/V2': "Deletes a previously enrolled card, removing it from Mastercard Checkout Solutions.",
    '/BulkEnrollmentOnC2P/V2': "Enrolls a batch of cards/consumers asynchronously in one call.",
    '/GetC2PBatchResult/V2': "Retrieves the status and per-card/consumer results of an asynchronous batch enrollment.",
}


def _is_gap(status, reliable):
    """Same rule as predig_adapter.py's _is_gap() -- states what differs,
    doesn't rank how much it matters."""
    if not reliable:
        return True
    return status in ("non_implemente", "partiel")


def _card_from_entry(data_path, entry):
    ep_name = data_path.lstrip('/').split('/')[0]
    if not entry.get("endpoint_exists_in_mcs"):
        return {
            "ep_name": ep_name, "path": data_path, "implemented": False,
            "error": "Endpoint not found in the official Mastercard Checkout Solutions spec.",
            "missing_count": 0, "missing_fields": [], "all_fields": [],
            "card_state": "na",
        }
    if not entry["endpoint_exists_in_data"]:
        return {
            "ep_name": ep_name, "path": data_path, "implemented": False, "error": None,
            "missing_count": len(entry["fields"]), "missing_fields": [], "all_fields": [],
            "card_state": "ecart",
        }

    missing_fields = []
    all_fields = []
    for f in entry["fields"]:
        is_gap = _is_gap(f["status"], f["reliable"])
        field_entry = {
            "field": f["name"], "is_gap": is_gap, "required": f.get("required"),
            "description": "; ".join(f.get("reasons") or []) or None,
        }
        all_fields.append(field_entry)
        if is_gap:
            missing_fields.append(field_entry)

    card_state = "ecart" if missing_fields else "conforme"

    return {
        "ep_name": ep_name, "path": data_path, "implemented": True, "error": None,
        "missing_count": len(missing_fields), "missing_fields": missing_fields, "all_fields": all_fields,
        "card_state": card_state,
    }


def _load_comparison_cache():
    if not os.path.exists(COMPARISON_CACHE_PATH):
        return None
    with open(COMPARISON_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_comparison_cache(payload):
    with open(COMPARISON_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _compute_comparison():
    card_spec = p1.load_spec(mcs.CARD_SPEC_PATH)
    batch_spec = p1.load_spec(mcs.BATCH_SPEC_PATH)
    data_spec = p1.load_spec(p1.DEFAULT_DATA_YAML, repair=True)
    mcs_direct = mcs.audit_mcs_vs_data_direct(card_spec, batch_spec, data_spec)

    cards = [_card_from_entry(data_path, mcs_direct[data_path]) for data_path, *_ in mcs.PRIORITY_OPERATIONS]

    total_missing = sum(c["missing_count"] for c in cards)
    n_with_gaps = sum(1 for c in cards if c["missing_count"])
    n_compliant = sum(1 for c in cards if c["card_state"] == "conforme")

    generated_at = None
    if os.path.exists(mcs.META_PATH):
        with open(mcs.META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        try:
            generated_at = datetime.fromisoformat(meta["fetched_at"]).strftime("%d/%m/%Y %H:%M")
        except (KeyError, ValueError):
            generated_at = meta.get("fetched_at")

    payload = {
        "generated_at": generated_at,
        "kpis": {
            "total_missing": total_missing, "n_with_gaps": n_with_gaps,
            "n_compliant": n_compliant, "n_total": len(cards),
        },
        "cards": cards,
    }
    _save_comparison_cache(payload)
    return payload


def get_comparison(refresh=False):
    if refresh:
        mcs.fetch_specs()

    if not os.path.exists(mcs.CARD_SPEC_PATH) or not os.path.exists(mcs.BATCH_SPEC_PATH):
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
    card_spec = p1.load_spec(mcs.CARD_SPEC_PATH)
    batch_spec = p1.load_spec(mcs.BATCH_SPEC_PATH)
    data_spec = p1.load_spec(p1.DEFAULT_DATA_YAML, repair=True)
    mcs_direct = mcs.audit_mcs_vs_data_direct(card_spec, batch_spec, data_spec)
    xlsx_path = dated_report_path(REPORTS_DIR, NETWORK_SLUG, "report")
    mcs.render_report_xlsx(mcs_direct, xlsx_path)
    return xlsx_path


def get_releases_timeline(refresh=False, date_from=None, date_to=None, endpoint=None):
    return {"has_run": False}


def export_releases_xlsx():
    return None


def get_email_data(view):
    if view == "releases":
        return {"has_data": False}
    comparison = get_comparison(refresh=False)
    if not comparison.get("has_run"):
        return {"has_data": False}
    subject = f"[Mastercard Checkout Solutions] Comparison — {comparison['kpis']['total_missing']} gap(s)"
    intro_lines = [f"{comparison['kpis']['total_missing']} missing field(s) across {comparison['kpis']['n_total']} tracked endpoint(s)."]
    for c in comparison["cards"]:
        if c["missing_count"]:
            intro_lines.append(f"- {c['path']}: {c['missing_count']} missing field(s)")
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
        return "success", f"Email sent to {', '.join(sent_to)}."
    except send_email_module.SmtpConfigError as e:
        return "error", str(e)


def endpoints_config():
    return [{"name": data_path.lstrip('/').split('/')[0],
             "description": OPERATION_DESCRIPTIONS.get(data_path, display)}
            for data_path, _, _, _, display in mcs.PRIORITY_OPERATIONS]


def endpoint_names():
    return [data_path.lstrip('/').split('/')[0] for data_path, *_ in mcs.PRIORITY_OPERATIONS]
