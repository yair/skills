#!/usr/bin/env python3
"""Send email via SMTP and save a copy to IMAP Sent folder.

Multi-agent: reads FROM_ADDR, FROM_NAME, PW_FILE from env vars,
or falls back to defaults based on the calling agent's workspace.

Usage:
    from send_email import send_email
    send_email(
        to=["someone@example.com"],
        subject="Subject here",
        body="<html>...</html>",
        content_type="html",
    )

Or from CLI:
    python3 send_email.py --to someone@example.com --subject "Test" --body "Hello"
"""
import imaplib
import smtplib
import ssl
import os
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate, make_msgid
from email.header import Header

SMTP_HOST = "127.0.0.1"
SMTP_PORT = 587
IMAP_HOST = "127.0.0.1"
IMAP_PORT = 993

# Agent identity — override with env vars or detect from workspace
_AGENTS = {
    "zeresh": {
        "addr": "zeresh@albanialink.com",
        "name": "Zeresh 😈",
        "pw_file": "/home/oc/.openclaw/workspace/.secrets/zeresh-email-pass",
    },
    "fay": {
        "addr": "fay@albanialink.com",
        "name": "Fay 🧚‍♀️",
        "pw_file": "/home/oc/.openclaw/workspace/.secrets/fay-email-pass",
    },
    "david": {
        "addr": "david@albanialink.com",
        "name": "David 🤙",
        "pw_file": "/home/oc/.openclaw/workspace/.secrets/david-email-pass",
    },
}

def _detect_agent():
    """Detect which agent we are from env or cwd."""
    agent = os.environ.get("AGENT_ID", "").lower()
    if agent in _AGENTS:
        return agent
    cwd = os.getcwd()
    if "workspace-shiri" in cwd:
        return "fay"
    elif "workspace-assaf" in cwd:
        return "david"
    return "zeresh"

def _get_identity():
    agent = _detect_agent()
    cfg = _AGENTS.get(agent, _AGENTS["zeresh"])
    return (
        os.environ.get("FROM_ADDR", cfg["addr"]),
        os.environ.get("FROM_NAME", cfg["name"]),
        os.environ.get("PW_FILE", cfg["pw_file"]),
    )

def _get_password(pw_file):
    return open(pw_file).read().strip()

def _make_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def send_email(to, subject, body, cc=None, bcc=None, content_type="html",
               from_addr=None, from_name=None):
    """Send email via SMTP and save copy to IMAP Sent folder."""
    _addr, _name, _pw_file = _get_identity()
    from_addr = from_addr or _addr
    from_name = from_name or _name
    pw = _get_password(_pw_file)

    if isinstance(to, str):
        to = [to]
    cc = cc or []
    bcc = bcc or []
    if isinstance(cc, str):
        cc = [cc]
    if isinstance(bcc, str):
        bcc = [bcc]

    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), from_addr))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="albanialink.com")
    msg.attach(MIMEText(body, content_type, "utf-8"))

    all_recipients = to + cc + bcc
    ctx = _make_ssl_ctx()

    # Send via SMTP
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=ctx)
        smtp.login(from_addr, pw)
        smtp.sendmail(from_addr, all_recipients, msg.as_string())

    # Save to IMAP Sent folder
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx) as imap:
            imap.login(from_addr, pw)
            imap.append("Sent", "\\Seen", imaplib.Time2Internaldate(time.time()),
                       msg.as_bytes())
    except Exception as e:
        print(f"Warning: IMAP save failed: {e}", file=sys.stderr)

    return msg["Message-ID"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send email")
    parser.add_argument("--to", required=True, nargs="+")
    parser.add_argument("--cc", nargs="+", default=[])
    parser.add_argument("--bcc", nargs="+", default=[])
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--content-type", default="plain", choices=["plain", "html"])
    args = parser.parse_args()
    mid = send_email(args.to, args.subject, args.body, args.cc, args.bcc, args.content_type)
    print(f"Sent: {mid}")
