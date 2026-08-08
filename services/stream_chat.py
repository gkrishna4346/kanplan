"""
Stream Chat integration for KanPlan's "Convo" feature.

Design:
- One "team" channel per Workspace, auto-created and kept in sync with
  WorkspaceMember rows (join a workspace -> auto-added to its channel;
  removed from workspace -> auto-removed from its channel).
- 1-on-1 DMs use Stream's "messaging" channel type with a distinct-members
  channel id, created on demand the first time two users open a chat.

This module is safe to import even before STREAM_API_KEY / STREAM_API_SECRET
are set in .env — every function no-ops (returns None) instead of raising,
the same "deferred setup, clear error later" pattern used for Google Sheets
sync elsewhere in this app. Once the env vars are set, everything works
without any code changes.
"""

from flask import current_app
from stream_chat import StreamChat

_client = None


def get_client():
    """Returns a configured StreamChat client, or None if not set up yet."""
    global _client
    api_key = current_app.config.get("STREAM_API_KEY")
    api_secret = current_app.config.get("STREAM_API_SECRET")

    if not api_key or not api_secret:
        return None

    if _client is None:
        _client = StreamChat(api_key=api_key, api_secret=api_secret)
    return _client


def is_configured():
    return get_client() is not None


def team_channel_id(workspace_id):
    # Stream channel ids must be <= 64 chars, alphanumeric/hyphen/underscore —
    # workspace UUIDs already satisfy that.
    return f"team-{workspace_id}"


def dm_channel_id(user_id_a, user_id_b):
    # Deterministic id so re-opening a DM reuses the same channel instead of
    # creating duplicates each time.
    a, b = sorted([user_id_a, user_id_b])
    return f"dm-{a[:8]}-{b[:8]}"


def upsert_user(user):
    """Create/update this user's profile on Stream (name, avatar)."""
    client = get_client()
    if not client:
        return
    client.upsert_user({
        "id": user.id,
        "name": user.name,
        "image": user.avatar_url,
    })


def generate_token(user_id):
    """Frontend needs this to authenticate as the current user with Stream."""
    client = get_client()
    if not client:
        return None
    return client.create_token(user_id)


def get_or_create_team_channel(workspace_id, workspace_name, member_ids):
    """Ensures the workspace's group channel exists with exactly these members."""
    client = get_client()
    if not client:
        return None

    channel = client.channel(
        "messaging",
        team_channel_id(workspace_id),
        data={"name": workspace_name, "members": member_ids, "created_by_id": member_ids[0]},
    )
    channel.create(member_ids[0])
    return channel


def add_member_to_workspace_channel(workspace_id, user_id, workspace_name="Team"):
    """Call this whenever someone joins a Workspace (new signup or accepted invite).
    Idempotent — safe to call even if they're already a channel member."""
    client = get_client()
    if not client:
        return

    channel = client.channel("messaging", team_channel_id(workspace_id))
    try:
        channel.add_members([user_id])
    except Exception:
        # Channel may not exist yet (e.g. very first member) — create it instead.
        channel.create(user_id)
        channel.add_members([user_id])


def ensure_synced(user, workspace_id, workspace_name="Team"):
    """Self-healing sync: makes sure this user's Stream profile exists AND they're
    a member of their workspace's team channel, regardless of whether the
    login-time sync in auth.py ever ran for them (e.g. they were already logged
    in before Stream was configured, or a prior sync attempt silently failed).
    Safe to call on every /convo page load — upsert_user and add_members are
    both idempotent on Stream's side, so this is cheap and has no side effects
    for someone who's already fully synced."""
    client = get_client()
    if not client:
        return
    upsert_user(user)
    add_member_to_workspace_channel(workspace_id, user.id, workspace_name=workspace_name)


def remove_member_from_workspace_channel(workspace_id, user_id):
    """Call this whenever someone is removed from a Workspace."""
    client = get_client()
    if not client:
        return

    channel = client.channel("messaging", team_channel_id(workspace_id))
    channel.remove_members([user_id])


def get_or_create_dm_channel(current_user_id, other_user_id):
    client = get_client()
    if not client:
        return None

    channel = client.channel(
        "messaging",
        dm_channel_id(current_user_id, other_user_id),
        data={"members": [current_user_id, other_user_id]},
    )
    channel.create(current_user_id)
    return channel
