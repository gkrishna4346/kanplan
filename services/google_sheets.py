"""
Handles syncing a workspace's tasks to a Google Sheet the user owns.

This calls the Google Sheets API v4 directly over HTTP (no heavy SDK
dependency) using the user's stored OAuth tokens.

IMPORTANT - read before relying on this in production:
This module has been reviewed carefully against Google's documented API
behavior, but it has NOT been exercised against the real Google Sheets API
in this environment (that requires live OAuth credentials this sandbox
doesn't have). The person deploying this should do one real end-to-end
test (Settings -> Sync Now) before trusting it, and report back if
anything doesn't match what's described here.
"""
import requests
from datetime import datetime, timedelta

from database.models import db

TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsSyncError(Exception):
    pass


def _refresh_access_token(user, client_id, client_secret):
    """Get a fresh access_token using the stored refresh_token."""
    if not user.google_refresh_token:
        raise SheetsSyncError(
            "No Google refresh token on file. Please log out and log back in "
            "to grant Sheets access."
        )

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": user.google_refresh_token,
        "grant_type": "refresh_token",
    })

    if resp.status_code != 200:
        raise SheetsSyncError(
            f"Could not refresh Google access token ({resp.status_code}). "
            "Try logging out and back in to re-grant access."
        )

    data = resp.json()
    user.google_access_token = data["access_token"]
    user.google_token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    db.session.commit()
    return user.google_access_token


def _get_valid_access_token(user, client_id, client_secret):
    """Return a usable access token, refreshing it first if it's expired or missing."""
    if (
        user.google_access_token
        and user.google_token_expiry
        and user.google_token_expiry > datetime.utcnow() + timedelta(minutes=2)
    ):
        return user.google_access_token
    return _refresh_access_token(user, client_id, client_secret)


def _create_spreadsheet(access_token, title):
    resp = requests.post(
        SHEETS_API,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Tasks"}}],
        },
    )
    if resp.status_code != 200:
        raise SheetsSyncError(f"Could not create spreadsheet ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    return data["spreadsheetId"], data["spreadsheetUrl"]


def _write_rows(access_token, sheet_id, rows):
    """Overwrites the 'Tasks' sheet's content with the given rows (header + data)."""
    range_ = "Tasks!A1"
    resp = requests.put(
        f"{SHEETS_API}/{sheet_id}/values/{range_}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"valueInputOption": "RAW"},
        json={"values": rows},
    )
    if resp.status_code != 200:
        raise SheetsSyncError(f"Could not write to spreadsheet ({resp.status_code}): {resp.text[:200]}")


def sync_workspace_to_sheet(user, workspace, tasks, client_id, client_secret):
    """
    Creates the workspace's backup sheet if it doesn't exist yet, then
    overwrites it with the current task list. Returns the sheet's URL.
    """
    access_token = _get_valid_access_token(user, client_id, client_secret)

    if not workspace.sheet_id:
        sheet_id, sheet_url = _create_spreadsheet(access_token, f"KanPlan - {workspace.name}")
        workspace.sheet_id = sheet_id
        workspace.sheet_url = sheet_url
        db.session.commit()

    header = [
        "Title", "Description", "Priority", "Status", "Due Date",
        "Tags", "Owner", "Created By", "Created Date", "Last Updated",
    ]
    rows = [header]
    for t in tasks:
        rows.append([
            t.title,
            t.description or "",
            t.priority,
            t.status,
            t.due_date.isoformat() if t.due_date else "",
            t.tags or "",
            t.assignee.name if t.assignee else "",
            t.created_by.name if t.created_by else "",
            t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            t.updated_at.strftime("%Y-%m-%d %H:%M") if t.updated_at else "",
        ])

    _write_rows(access_token, workspace.sheet_id, rows)

    workspace.last_synced_at = datetime.utcnow()
    db.session.commit()

    return workspace.sheet_url
