"""
report_naming.py — one dated Excel filename convention shared by every
adapter's export_*_xlsx(), so a report downloaded from the History page (or
attached to an email) always says which volet/network it came from at a
glance, instead of a generic name shared across all three -- e.g.
'customer_service_report_19_08_26.xlsx' rather than 'divergence_report.xlsx'.

Date-only (no time-of-day): re-exporting the same day overwrites that day's
file rather than piling up near-duplicates in History, which matches how the
Comparaison page already treats "refresh" as replacing the current state, not
appending to it.
"""

import os
from datetime import datetime


def dated_report_path(reports_dir, network_slug, kind="report"):
    """kind='report' -> '<slug>_report_dd_mm_yy.xlsx'
    kind='releases_report' -> '<slug>_releases_report_dd_mm_yy.xlsx'"""
    date_part = datetime.now().strftime("%d_%m_%y")
    filename = f"{network_slug}_{kind}_{date_part}.xlsx"
    return os.path.join(reports_dir, filename)
