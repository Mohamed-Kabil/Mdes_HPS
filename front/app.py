#!/usr/bin/env python3
"""
front/app.py — Flask backend for the frontend_a_partager template system
(see ../../frontend_a_partager/INTEGRATION.md), wired to this project's real
data instead of placeholder content.

Two "networks" registered: predig (MDES Pre-Digitization, mc_divergence/) and
mdescs (MDES Customer Service, mdes_cs_divergence_report.py +
mdes_cs_prereleases.py). Both share one blueprint factory (build_network_blueprint)
since the frontend's route/section shape is identical for both — only the
adapter module backing each one differs (front/adapters/predig_adapter.py,
front/adapters/mdescs_adapter.py).

The original "mastercard"/"visa" demo network templates (templates/networks/mastercard/,
templates/networks/visa/) are kept on disk untouched but deliberately NOT
registered here -- they're generic placeholder content, not this project's
real data, and inventing fake data for them would be misleading. See
front/INTEGRATION_NOTES.md for the full list of gaps/decisions made while
wiring this up.

Usage:
    python3 front/app.py
    -> http://127.0.0.1:5000
"""

import os
import sys
from datetime import date, timedelta

from flask import Blueprint, Flask, redirect, render_template, request, send_from_directory, url_for
from markupsafe import escape

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "mc_divergence"))

from adapters import predig_adapter, mdescs_adapter
import notes_store
import env_store

REPORTS_DIR = os.path.join(PROJECT_ROOT, "mc_divergence", "reports")

app = Flask(__name__, template_folder="templates", static_folder="static")

NETWORKS = [
    {"key": "predig", "name": "MDES Pre-Digitization", "logo": "logos/mastercard.svg"},
    {"key": "mdescs", "name": "MDES Customer Service", "logo": "logos/mastercard.svg"},
]

SECTION_BY_FUNC = {
    "comparison_view": "comparaison", "comparison_detail": "comparaison",
    "releases_view": "releases",
    "email_view": "email",
    "historique_view": "historique", "historique_download": "historique",
    "configuration_view": "configuration",
    "notes_view": "notes",
}


@app.context_processor
def inject_globals():
    current_network_key = request.blueprint if request.blueprint in {"predig", "mdescs"} else None
    current_section = None
    if current_network_key and request.endpoint:
        func = request.endpoint.split(".", 1)[-1]
        current_section = SECTION_BY_FUNC.get(func)
    return dict(networks=NETWORKS, current_network_key=current_network_key, current_section=current_section)


# ============================================================================
# Global routes
# ============================================================================

@app.get("/")
def platform_home_view():
    return render_template("platform_home.html")


@app.route("/parametres", methods=["GET", "POST"])
def parametres_view():
    saved = False
    if request.method == "POST":
        updates = {
            "SMTP_HOST": request.form.get("smtp_server", ""),
            "SMTP_PORT": request.form.get("smtp_port", ""),
            "SMTP_USER": request.form.get("sender_email", ""),
            "SMTP_FROM": request.form.get("sender_email", ""),
            "MC_DIVERGENCE_RECIPIENTS": request.form.get("default_recipients", ""),
        }
        password = request.form.get("sender_password", "")
        if password:
            updates["SMTP_PASSWORD"] = password
        env_store.write_env(updates)
        saved = True

    values = env_store.read_env()
    return render_template(
        "parametres.html", saved=saved,
        smtp_server=values.get("SMTP_HOST", ""), smtp_port=values.get("SMTP_PORT", ""),
        sender_email=values.get("SMTP_USER", values.get("SMTP_FROM", "")),
        default_recipients=values.get("MC_DIVERGENCE_RECIPIENTS", ""),
    )


@app.get("/aide")
def aide_view():
    return render_template("aide.html")


# ============================================================================
# Per-network blueprint factory
# ============================================================================

def build_network_blueprint(key, name, adapter):
    bp = Blueprint(key, __name__, url_prefix=f"/{key}")

    @bp.get("/")
    def accueil_view():
        net = next(n for n in NETWORKS if n["key"] == key)
        has_run = adapter.get_comparison(refresh=False).get("has_run", False)
        return render_template(
            f"networks/{key}/accueil.html",
            primary_label="View comparison" if has_run else "Run analysis",
            primary_url=url_for(f"{key}.comparison_view", **({} if has_run else {"refresh": 1})),
            primary_disabled=False, primary_loading=not has_run,
        )

    @bp.get("/comparaison")
    def comparison_view():
        data = adapter.get_comparison(refresh=request.args.get("refresh") == "1")
        if not data.get("has_run"):
            return render_template(f"networks/{key}/comparison.html", has_run=False,
                                    refresh_url=url_for(f"{key}.comparison_view", refresh=1))

        return render_template(
            f"networks/{key}/comparison.html", has_run=True,
            refresh_url=url_for(f"{key}.comparison_view", refresh=1),
            generated_at=data["generated_at"], export_url=url_for(f"{key}.comparison_export"),
            kpis=data["kpis"], cards=data["cards"],
        )

    @bp.get("/comparaison/export")
    def comparison_export():
        path = adapter.export_comparison_xlsx()
        if not path or not os.path.exists(path):
            return "No report available — run an analysis first.", 404
        return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True)

    @bp.get("/comparaison/<path:endpoint_name>")
    def comparison_detail(endpoint_name):
        card = adapter.get_comparison_detail(endpoint_name)
        if card is None:
            return "Endpoint not found.", 404
        return render_template(f"networks/{key}/detail.html", path=card["path"], implemented=card["implemented"],
                                error=card["error"], all_fields=card["all_fields"])

    @bp.get("/releases")
    def releases_view():
        date_from = request.args.get("from") or None
        date_to = request.args.get("to") or None
        endpoint = request.args.get("ep") or None
        full = adapter.get_releases_timeline(refresh=request.args.get("refresh") == "1")
        if not full.get("has_run"):
            return render_template("networks/_releases_timeline.html", network_key=key, network_name=name,
                                    has_run=False, refresh_url=url_for(f"{key}.releases_view", refresh=1))
        years = sorted({t["date_sort"][:4] for t in full["timeline"] if t["date_sort"]}, reverse=True)
        data = adapter.get_releases_timeline(date_from=date_from, date_to=date_to, endpoint=endpoint)
        return render_template(
            "networks/_releases_timeline.html", network_key=key, network_name=name, has_run=True,
            generated_at=data["generated_at"], refresh_url=url_for(f"{key}.releases_view", refresh=1),
            export_url=url_for(f"{key}.releases_export"), kpis=data["kpis"],
            releases=data["timeline"], date_from=date_from, date_to=date_to,
            presets=_release_date_presets(years),
            endpoint=endpoint, endpoints=adapter.endpoint_names(),
        )

    @bp.get("/releases/export")
    def releases_export():
        path = adapter.export_releases_xlsx()
        if not path or not os.path.exists(path):
            return "No report available — run an analysis first.", 404
        return send_from_directory(os.path.dirname(path), os.path.basename(path), as_attachment=True)

    @bp.route("/email", methods=["GET", "POST"])
    def email_view():
        view = request.values.get("view", "comparison")
        data = adapter.get_email_data(view)

        if request.method == "POST":
            if not data.get("has_data"):
                return redirect(url_for(f"{key}.email_view", view=view))

            subject = request.form.get("subject", "")
            intro = request.form.get("intro", "")
            recipients = request.form.get("recipients", "")

            if request.form.get("confirmed") == "1":
                status, message = adapter.send_report_email(view, subject, intro, recipients)
                return render_template(
                    f"networks/{key}/email.html", view=view, has_data=True, result=(status, message),
                    pending_confirm=False, subject=subject, intro=intro, recipients=recipients,
                    preview_html=_preview_html(intro), attachment_name=data.get("attachment_name") or "(none)",
                )

            return render_template(
                f"networks/{key}/email.html", view=view, has_data=True, result=None, pending_confirm=True,
                subject=subject, intro=intro, recipients=recipients,
                preview_html=_preview_html(intro), attachment_name=data.get("attachment_name") or "(none)",
            )

        if not data.get("has_data"):
            return render_template(f"networks/{key}/email.html", view=view, has_data=False)

        default_recipients = env_store.read_env().get("MC_DIVERGENCE_RECIPIENTS", "")
        return render_template(
            f"networks/{key}/email.html", view=view, has_data=True, result=None, pending_confirm=False,
            subject=data["subject"], intro=data["intro"], recipients=default_recipients,
            preview_html=_preview_html(data["intro"]), attachment_name=data["attachment_name"],
        )

    @bp.get("/historique")
    def historique_view():
        reports = _list_reports(key)
        return render_template("networks/_historique.html", network_name=name, network_key=key, reports=reports)

    @bp.get("/historique/<path:name_>")
    def historique_download(name_):
        return send_from_directory(REPORTS_DIR, name_, as_attachment=True)

    @bp.get("/configuration")
    def configuration_view():
        return render_template("networks/_configuration.html", network_name=name, endpoints=adapter.endpoints_config())

    @bp.route("/notes", methods=["GET", "POST"])
    def notes_view():
        if request.method == "POST":
            notes_store.add_note(key, request.form.get("endpoint_name", ""),
                                  request.form.get("texte", ""), request.form.get("auteur", ""))
            return redirect(url_for(f"{key}.notes_view"))
        return render_template("networks/_notes.html", network_key=key, endpoints=adapter.endpoint_names(),
                                notes_by_endpoint=notes_store.load_notes(key))

    return bp


def _release_date_presets(years):
    """Quick filter chips for the releases timeline: relative windows plus
    one chip per year actually present in the data (newest first) -- swapped
    in for a manual from/to date-picker, which was fiddly to use for a
    quick 'what happened around when' scan.

    '3/6 derniers mois' are open-ended (from=N months ago, to=None) rather
    than a closed [today-N, today] window -- these are pre-release notes,
    many scheduled with a production date that hasn't happened yet, and a
    closed window silently hid every release still pending production
    (e.g. one dated for November while today is August)."""
    today = date.today()
    presets = [
        ("All", None, None),
        ("Last 3 months", (today - timedelta(days=90)).isoformat(), None),
        ("Last 6 months", (today - timedelta(days=180)).isoformat(), None),
        ("This year", f"{today.year}-01-01", f"{today.year}-12-31"),
    ]
    for y in years:
        presets.append((y, f"{y}-01-01", f"{y}-12-31"))
    return presets


def _preview_html(text):
    """Email bodies are plain multi-line text (see phase1_historical_audit.py's
    render_email_draft / mdes_cs_divergence_report.render_email_body) --
    escape + <pre> wrap rather than pulling in a markdown-to-HTML dependency
    just for this preview."""
    return f'<pre class="email-preview-pre">{escape(text)}</pre>'


def _list_reports(network_key):
    if not os.path.isdir(REPORTS_DIR):
        return []
    reports = []
    for name_ in os.listdir(REPORTS_DIR):
        path = os.path.join(REPORTS_DIR, name_)
        if not os.path.isfile(path):
            continue
        is_cs = name_.startswith("mdes_cs_")
        if network_key == "mdescs" and not is_cs:
            continue
        if network_key == "predig" and is_cs:
            continue
        stat = os.stat(path)
        from datetime import datetime
        reports.append({
            "name": name_,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "size": f"{stat.st_size / 1024:.1f} Ko" if stat.st_size < 1024 * 1024 else f"{stat.st_size / (1024*1024):.1f} Mo",
            "_mtime": stat.st_mtime,
        })
    reports.sort(key=lambda r: r["_mtime"], reverse=True)
    return reports


app.register_blueprint(build_network_blueprint("predig", "MDES Pre-Digitization", predig_adapter))
app.register_blueprint(build_network_blueprint("mdescs", "MDES Customer Service", mdescs_adapter))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
