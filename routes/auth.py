from datetime import datetime, timedelta

from flask import Blueprint, redirect, url_for, session
from flask_login import login_user, logout_user, login_required

from services.google_auth import oauth
from services.stream_chat import upsert_user, add_member_to_workspace_channel
from database.models import db, User, Workspace, WorkspaceMember, Invite

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login/google")
def login_google():
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/login/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")

    if not userinfo:
        return "Google login failed - no user info returned.", 400

    google_sub = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email.split("@")[0])
    picture = userinfo.get("picture")

    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")  # only present when prompt=consent forced re-approval
    expires_in = token.get("expires_in")
    token_expiry = (
        datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
    )

    user = User.query.filter_by(google_sub=google_sub).first()
    newly_joined_workspace = None  # (workspace_id, workspace_name) if set below

    if not user:
        user = User(
            google_sub=google_sub,
            email=email,
            name=name,
            avatar_url=picture,
        )
        db.session.add(user)
        db.session.flush()  # get user.id before creating/joining a workspace

        # Check for a pending invite matching this email
        invite = Invite.query.filter_by(email=email).first()

        if invite:
            membership = WorkspaceMember(
                workspace_id=invite.workspace_id, user_id=user.id, role=invite.role
            )
            db.session.add(membership)
            db.session.delete(invite)

            invited_workspace = Workspace.query.get(invite.workspace_id)
            newly_joined_workspace = (invite.workspace_id, invited_workspace.name if invited_workspace else "Team")
        else:
            # No invite found: first-time login creates a personal workspace + default board
            from database.models import Board

            workspace = Workspace(name=f"{name}'s Workspace")
            db.session.add(workspace)
            db.session.flush()

            membership = WorkspaceMember(
                workspace_id=workspace.id, user_id=user.id, role="admin"
            )
            db.session.add(membership)

            default_board = Board(workspace_id=workspace.id, name="Main Board")
            db.session.add(default_board)

            newly_joined_workspace = (workspace.id, workspace.name)
    else:
        # keep profile info fresh
        user.name = name
        user.avatar_url = picture

    # Save tokens (present on every login since prompt=consent forces re-approval each time)
    if access_token:
        user.google_access_token = access_token
    if refresh_token:
        user.google_refresh_token = refresh_token
    if token_expiry:
        user.google_token_expiry = token_expiry

    db.session.commit()

    # Sync to Stream Chat: create/update their profile, and if they just joined
    # a workspace (new signup or accepted invite), add them to its team channel.
    # Best-effort — if Stream isn't configured yet, these are safe no-ops.
    try:
        upsert_user(user)
        if newly_joined_workspace:
            ws_id, ws_name = newly_joined_workspace
            add_member_to_workspace_channel(ws_id, user.id, workspace_name=ws_name)
    except Exception:
        pass

    login_user(user)
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/login")
def login_page():
    from flask import render_template
    return render_template("login.html")
