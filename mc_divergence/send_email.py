#!/usr/bin/env python3
"""
send_email.py — thin SMTP sender shared by phase1_historical_audit.py and
phase2_job_a_new_release_alert.py.

No credentials live in code or in this repo. Everything comes from
environment variables, read fresh at call time:

    SMTP_HOST        required to actually send   (e.g. smtp.gmail.com,
                                                    smtp.office365.com, or an
                                                    internal HPS relay)
    SMTP_PORT        optional, default 587 (STARTTLS). Use 465 for SMTP_SSL.
    SMTP_USER        required unless the relay accepts unauthenticated mail
    SMTP_PASSWORD    required unless the relay accepts unauthenticated mail
                      -- for Gmail/Office365 this MUST be an app password,
                      not the account's normal login password (both block
                      plain SMTP auth by default, especially with 2FA on).
    SMTP_FROM        optional, defaults to SMTP_USER
    MC_DIVERGENCE_RECIPIENTS
                      comma-separated recipient list. Falls back to
                      DEFAULT_RECIPIENTS below if unset.

By design this raises a clear, actionable error rather than silently
skipping the send or falling back to anything else when config is missing
-- the caller decides whether to catch it (e.g. to still keep the local
'email divergence date - jj-mm-aa.md' file as a record either way).

Usage as a library:
    from send_email import send_email
    send_email(subject="...", body="...")

Usage as a CLI (mostly for testing the SMTP config in isolation):
    python3 send_email.py --subject "Test" --body "Hello" [--to a@b.com,c@d.com]
"""

import argparse
import mimetypes
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Recipient given directly (2026-07-09): destinataire par défaut tant que
# MC_DIVERGENCE_RECIPIENTS n'est pas défini.
DEFAULT_RECIPIENTS = ["simokabil03@gmail.com"]

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_dotenv(path=_ENV_FILE):
    """Loads KEY=VALUE lines from mc_divergence/.env into os.environ, without
    overwriting a variable that's already set in the real environment (a real
    env var / one set in the calling shell always wins over the file). Silent
    no-op if the file doesn't exist -- .env is optional, not required."""
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


class SmtpConfigError(RuntimeError):
    """Raised when required SMTP env vars are missing — deliberately loud,
    per the agreed behaviour: never silently skip a send, never silently
    fall back to writing a file instead (the caller can choose to do that,
    but this function itself must fail clearly)."""


def _get_recipients():
    raw = os.environ.get('MC_DIVERGENCE_RECIPIENTS')
    if raw:
        return [addr.strip() for addr in raw.split(',') if addr.strip()]
    return DEFAULT_RECIPIENTS


def send_email(subject, body, recipients=None, attachments=None):
    """attachments: optional list of file paths to attach as-is (e.g. the
    full Markdown divergence report) -- the body stays a short, readable
    summary and the report travels alongside it rather than being pasted
    inline."""
    host = os.environ.get('SMTP_HOST')
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    port = int(os.environ.get('SMTP_PORT') or '587')
    sender = os.environ.get('SMTP_FROM') or user

    missing = [name for name, val in (('SMTP_HOST', host),) if not val]
    if missing:
        raise SmtpConfigError(
            f"Variable(s) d'environnement manquante(s) pour l'envoi SMTP : {', '.join(missing)}. "
            "Aucun email envoyé. Définis au minimum SMTP_HOST (+ SMTP_USER/SMTP_PASSWORD si le "
            "relais exige une authentification) avant de relancer avec --send."
        )
    if not sender:
        raise SmtpConfigError(
            "SMTP_FROM (ou SMTP_USER en repli) n'est pas défini — impossible de déterminer "
            "l'expéditeur. Aucun email envoyé."
        )

    to_list = recipients or _get_recipients()
    if not to_list:
        raise SmtpConfigError("Aucun destinataire — MC_DIVERGENCE_RECIPIENTS est vide. Aucun email envoyé.")

    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        for path in attachments:
            if not os.path.exists(path):
                raise SmtpConfigError(f"Pièce jointe introuvable : {path}. Aucun email envoyé.")
            ctype, _ = mimetypes.guess_type(path)
            _, subtype = (ctype.split('/', 1) if ctype else ('application', 'octet-stream'))
            with open(path, 'rb') as f:
                part = MIMEApplication(f.read(), _subtype=subtype)
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
            msg.attach(part)
    else:
        msg = MIMEText(body, 'plain', 'utf-8')

    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(to_list)

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()

    try:
        if user and password:
            server.login(user, password)
        server.sendmail(sender, to_list, msg.as_string())
    finally:
        server.quit()

    return to_list


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--subject', required=True)
    parser.add_argument('--body', required=True)
    parser.add_argument('--to', help="comma-separated, overrides MC_DIVERGENCE_RECIPIENTS")
    parser.add_argument('--attach', action='append', help="file path to attach, repeatable")
    args = parser.parse_args()

    recipients = [a.strip() for a in args.to.split(',')] if args.to else None
    try:
        sent_to = send_email(args.subject, args.body, recipients=recipients, attachments=args.attach)
    except SmtpConfigError as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Email envoyé à : {', '.join(sent_to)}")


if __name__ == '__main__':
    main()
