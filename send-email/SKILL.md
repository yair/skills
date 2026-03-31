---
name: send-email
description: >
  Send email via SMTP with IMAP sent-folder copy. Multi-agent: auto-detects
  sender identity from workspace path (Zeresh, Fay, David). Use when the agent
  needs to send an email, forward information, or deliver files to someone
  outside the messaging platform. Supports HTML and plain text, TO/CC/BCC.
  Do NOT use for internal agent-to-agent communication (use sessions_send
  or message tool instead).
---

# Send Email Skill

## When to Use
- Sending information to someone who isn't on Telegram/Discord/WhatsApp
- Delivering reports, documents, or files via email
- Replying to incoming emails
- BCCing Jay on client communications

## When NOT to Use
- Internal agent communication → use `sessions_send`
- Messaging Jay → use Telegram `message` tool
- Sending to Shiri/Assaf → Telegram is faster, use email only if they asked for it

## Script

```bash
python3 scripts/send_email.py --to recipient@example.com --subject "Subject" --body "Body text" --content-type plain
```

Or from Python:
```python
from send_email import send_email
send_email(
    to=["recipient@example.com"],
    cc=["cc@example.com"],
    subject="Subject Line",
    body="<p>HTML body</p>",
    content_type="html"
)
```

## Identity Auto-Detection

The script detects the calling agent from the workspace path:
- `workspace/` or `workspace-main/` → `zeresh@albanialink.com` (Zeresh 😈)
- `workspace-shiri/` → `fay@albanialink.com` (Fay 🧚‍♀️)
- `workspace-assaf/` → `david@albanialink.com` (David 🤙)

Override with `from_addr` and `from_name` parameters if needed.

## SMTP Configuration

- Host: `127.0.0.1:587` (STARTTLS) — LOCALHOST, not the domain name
- Passwords: `/home/oc/.openclaw/workspace/.secrets/{agent}-email-pass`
- Saves copy to IMAP Sent folder automatically

## Edge Cases
- **Large attachments:** Email has ~25MB limit. For larger files, share via SyncThing or upload and send link.
- **HTML vs plain:** Use `content_type="html"` for formatted reports, `"plain"` for simple messages.
- **SMTP failure:** Script prints warning but doesn't crash. Check `/var/log/mail.log` if emails don't arrive.
- **IMAP save failure:** Warning only. Email still sends even if Sent folder save fails.

## Quality Gate
- [ ] Email arrives at recipient (check for bounce-backs)
- [ ] Sent copy appears in IMAP Sent folder
- [ ] From address matches the calling agent
- [ ] Subject line is meaningful (not empty or generic)
- [ ] BCC Jay on client communications (when appropriate)
