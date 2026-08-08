from flask import Blueprint, render_template, request, current_app
from flask_login import login_required, current_user

from database.models import WorkspaceMember, Workspace
from services.stream_chat import (
    is_configured,
    generate_token,
    team_channel_id,
    dm_channel_id,
    ensure_synced,
)

video_bp = Blueprint("video", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


@video_bp.route("/video")
@login_required
def view_video():
    configured = is_configured()

    if not configured:
        return render_template("video.html", configured=False)

    workspace_id = _current_workspace_id()
    workspace = Workspace.query.get(workspace_id)

    # Same self-healing sync pattern as Convo — video and chat share one Stream
    # app/user base, so this also covers anyone who's never opened Convo yet.
    ensure_synced(current_user, workspace_id, workspace_name=workspace.name if workspace else "Team")
    token = generate_token(current_user.id)

    teammates = (
        WorkspaceMember.query
        .filter_by(workspace_id=workspace_id)
        .join(WorkspaceMember.user)
        .filter(WorkspaceMember.user_id != current_user.id)
        .all()
    )

    # Deep-link support: Convo's "Call" button lands here with ?call=<id>&label=<name>
    # so both entry points (Convo button, and this page's own sidebar) drive the
    # same call UI instead of two separate implementations.
    preset_call_id = request.args.get("call")
    preset_label = request.args.get("label")

    return render_template(
        "video.html",
        configured=True,
        stream_api_key=current_app.config.get("STREAM_API_KEY"),
        stream_token=token,
        user_id=current_user.id,
        user_name=current_user.name,
        user_avatar=current_user.avatar_url or "",
        team_call_id=team_channel_id(workspace_id),
        teammates=[
            {
                "id": m.user.id,
                "name": m.user.name,
                "initials": m.user.initials(),
                "call_id": dm_channel_id(current_user.id, m.user.id),
            }
            for m in teammates
        ],
        preset_call_id=preset_call_id,
        preset_label=preset_label,
    )
