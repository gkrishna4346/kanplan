"""
Handles reading and sending mail via the Gmail API, using the user's own
Google account (the same one they log into KanPlan with).

Calls the Gmail API v4 directly over HTTP (no heavy SDK dependency),
following the exact same token-storage/refresh pattern as
services/google_sheets.py -- see that file for the original design notes.

IMPORTANT - read before relying on this in production:
Like Sheets sync, this has been written carefully against Google's
documented Gmail API behavior but has NOT been exercised against a real
Gmail account in this environment (no live OAuth credentials here). Do one
real end-to-end test (open Mail, send yourself a test email) before
trusting it, and report back anything that doesn't match.

Scope note: anyone who logged into KanPlan before Gmail scopes were added
to services/google_auth.py has a refresh_token that does NOT cover Gmail.
Calls below will get a 403 from Google in that case -- MailScopeError is
raised specifically so routes/mail.py can show "log out and back in" rather
than a raw API error.
"""
import base64
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from database.models import db

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class MailError(Exception):
    pass


class MailScopeError(MailError):
    """Raised when the user's token doesn't cover Gmail scopes yet (needs re-login)."""
    pass


def _refresh_access_token(user, client_id, client_secret):
    if not user.google_refresh_token:
        raise MailError("No Google refresh token on file. Please log out and log back in to grant Mail access.")

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": user.google_refresh_token,
        "grant_type": "refresh_token",
    })
    if resp.status_code != 200:
        raise MailError(f"Could not refresh Google access token ({resp.status_code}). Try logging out and back in.")

    data = resp.json()
    user.google_access_token = data["access_token"]
    user.google_token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    db.session.commit()
    return user.google_access_token


def _get_valid_access_token(user, client_id, client_secret):
    if (
        user.google_access_token
        and user.google_token_expiry
        and user.google_token_expiry > datetime.utcnow() + timedelta(minutes=2)
    ):
        return user.google_access_token
    return _refresh_access_token(user, client_id, client_secret)


def _gmail_get(access_token, path, params=None):
    resp = requests.get(f"{GMAIL_API}/{path}", headers={"Authorization": f"Bearer {access_token}"}, params=params)
    if resp.status_code == 403:
        raise MailScopeError(
            "Your Google login doesn't have Mail access yet. Log out and log back in to grant it."
        )
    if resp.status_code != 200:
        raise MailError(f"Gmail API error ({resp.status_code}): {resp.text[:200]}")
    return resp.json()


def _header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body_part(part):
    """Walks a Gmail message payload to find the best text body (prefers plain text)."""
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", errors="replace")

    if part.get("mimeType") == "text/html" and part.get("body", {}).get("data") and not part.get("_has_plain"):
        html = base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", errors="replace")
        return html  # rendered as-is; template escapes it, so raw HTML tags just show as text if not trusted

    for sub in part.get("parts", []) or []:
        result = _decode_body_part(sub)
        if result:
            return result
    return ""


def list_inbox(user, client_id, client_secret, max_results=25):
    """Returns a list of {id, subject, from, snippet, date, unread} — list-view metadata only,
    not full bodies (keeps this fast; full body is fetched on demand in get_message)."""
    access_token = _get_valid_access_token(user, client_id, client_secret)

    listing = _gmail_get(access_token, "messages", params={"maxResults": max_results, "labelIds": "INBOX"})
    message_ids = [m["id"] for m in listing.get("messages", [])]

    results = []
    for mid in message_ids:
        meta = _gmail_get(
            access_token, f"messages/{mid}",
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
        )
        headers = meta.get("payload", {}).get("headers", [])
        results.append({
            "id": mid,
            "subject": _header(headers, "Subject") or "(no subject)",
            "from": _header(headers, "From"),
            "date": _header(headers, "Date"),
            "snippet": meta.get("snippet", ""),
            "unread": "UNREAD" in meta.get("labelIds", []),
        })
    return results


def get_message(user, client_id, client_secret, message_id):
    """Fetches one message's full body and marks it read."""
    access_token = _get_valid_access_token(user, client_id, client_secret)

    msg = _gmail_get(access_token, f"messages/{message_id}", params={"format": "full"})
    headers = msg.get("payload", {}).get("headers", [])
    body = _decode_body_part(msg.get("payload", {})) or msg.get("snippet", "")

    # Mark as read (best-effort — a failure here shouldn't block showing the message)
    try:
        requests.post(
            f"{GMAIL_API}/messages/{message_id}/modify",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"removeLabelIds": ["UNREAD"]},
        )
    except Exception:
        pass

    return {
        "id": message_id,
        "subject": _header(headers, "Subject") or "(no subject)",
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "date": _header(headers, "Date"),
        "body": body,
    }


def send_message(user, client_id, client_secret, to, subject, body):
    access_token = _get_valid_access_token(user, client_id, client_secret)

    mime = MIMEText(body)
    mime["to"] = to
    mime["from"] = user.email
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")

    resp = requests.post(
        f"{GMAIL_API}/messages/send",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"raw": raw},
    )
    if resp.status_code == 403:
        raise MailScopeError("Your Google login doesn't have Mail access yet. Log out and log back in to grant it.")
    if resp.status_code != 200:
        raise MailError(f"Could not send email ({resp.status_code}): {resp.text[:200]}")
    return resp.json()
