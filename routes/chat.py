from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user

from database.models import WorkspaceMember, Workspace, User
from services.stream_chat import (
    is_configured,
    generate_token,
    team_channel_id,
    get_or_create_dm_channel,
    ensure_synced,
    upsert_user,
)

chat_bp = Blueprint("chat", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


@chat_bp.route("/convo")
@login_required
def view_convo():
    configured = is_configured()

    if not configured:
        return render_template("convo.html", configured=False)

    workspace_id = _current_workspace_id()

    # Self-healing sync: guarantees this user has a valid Stream profile and is
    # a member of their team channel, even if the login-time sync (auth.py)
    # never ran for them — e.g. they were already logged in before Stream was
    # configured. Cheap and idempotent, safe to run on every page load.
    workspace = Workspace.query.get(workspace_id)
    ensure_synced(current_user, workspace_id, workspace_name=workspace.name if workspace else "Team")

    token = generate_token(current_user.id)

    teammates = (
        WorkspaceMember.query
        .filter_by(workspace_id=workspace_id)
        .join(WorkspaceMember.user)
        .filter(WorkspaceMember.user_id != current_user.id)
        .all()
    )

    return render_template(
        "convo.html",
        configured=True,
        stream_api_key=current_app.config.get("STREAM_API_KEY"),
        stream_token=token,
        user_id=current_user.id,
        user_name=current_user.name,
        user_avatar=current_user.avatar_url or "",
        team_channel_id=team_channel_id(workspace_id),
        teammates=[{"id": m.user.id, "name": m.user.name, "initials": m.user.initials()} for m in teammates],
    )


@chat_bp.route("/api/chat/dm/<other_user_id>", methods=["POST"])
@login_required
def start_dm(other_user_id):
    """Creates (or fetches the existing) 1-on-1 channel with a teammate."""
    if not is_configured():
        return jsonify({"error": "Chat isn't set up yet."}), 503

    other_user = User.query.get(other_user_id)
    if not other_user:
        return jsonify({"error": "That teammate no longer exists."}), 404

    try:
        # Make sure both sides exist as valid Stream users before creating the
        # channel — otherwise Stream rejects it if either person hasn't been
        # upserted yet (e.g. they've never opened Convo, or logged in before
        # Stream was configured).
        upsert_user(current_user)
        upsert_user(other_user)
        channel = get_or_create_dm_channel(current_user.id, other_user_id)
        return jsonify({"channel_id": channel.id, "channel_type": "messaging"})
    except Exception as e:
        return jsonify({"error": f"Couldn't create the chat: {str(e)}"}), 500
