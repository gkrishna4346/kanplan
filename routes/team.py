from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from database.models import db, WorkspaceMember, Invite, User
from services.stream_chat import remove_member_from_workspace_channel

team_bp = Blueprint("team", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


def _current_role():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.role if membership else None


@team_bp.route("/team")
@login_required
def view_team():
    workspace_id = _current_workspace_id()

    members = (
        WorkspaceMember.query
        .filter_by(workspace_id=workspace_id)
        .join(WorkspaceMember.user)
        .order_by(WorkspaceMember.joined_at)
        .all()
    )
    invites = (
        Invite.query
        .filter_by(workspace_id=workspace_id)
        .order_by(Invite.created_at)
        .all()
    )

    return render_template(
        "team.html",
        members=members,
        invites=invites,
        current_role=_current_role(),
    )


@team_bp.route("/api/invites", methods=["POST"])
@login_required
def create_invite():
    workspace_id = _current_workspace_id()
    email = (request.json.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Already a member?
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        already_member = WorkspaceMember.query.filter_by(
            workspace_id=workspace_id, user_id=existing_user.id
        ).first()
        if already_member:
            return jsonify({"error": "This person is already on the team."}), 400

    # Already invited?
    existing_invite = Invite.query.filter_by(workspace_id=workspace_id, email=email).first()
    if existing_invite:
        return jsonify({"error": "An invite is already pending for this email."}), 400

    invite = Invite(
        workspace_id=workspace_id,
        email=email,
        invited_by_id=current_user.id,
        role="member",
    )
    db.session.add(invite)
    db.session.commit()

    return jsonify({"id": invite.id, "email": invite.email}), 201


@team_bp.route("/api/invites/<invite_id>", methods=["DELETE"])
@login_required
def delete_invite(invite_id):
    invite = Invite.query.get_or_404(invite_id)
    db.session.delete(invite)
    db.session.commit()
    return "", 204


@team_bp.route("/api/team/members/<member_id>", methods=["DELETE"])
@login_required
def remove_member(member_id):
    """Admin-only: remove a member from the workspace (and its chat channel)."""
    if _current_role() != "admin":
        return jsonify({"error": "Only admins can remove members."}), 403

    workspace_id = _current_workspace_id()
    membership = WorkspaceMember.query.filter_by(
        id=member_id, workspace_id=workspace_id
    ).first_or_404()

    if membership.user_id == current_user.id:
        return jsonify({"error": "You can't remove yourself. Ask another admin."}), 400

    removed_user_id = membership.user_id
    db.session.delete(membership)
    db.session.commit()

    # Keep chat access in sync: losing workspace access also loses the team channel.
    # Best-effort — if Stream isn't configured or the call fails, membership removal
    # (the part that actually matters for security) has already succeeded.
    try:
        remove_member_from_workspace_channel(workspace_id, removed_user_id)
    except Exception:
        pass

    return "", 204
