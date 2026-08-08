import csv
import io

from flask import Blueprint, render_template, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from database.models import db, Task, Board, WorkspaceMember, Workspace
from services.google_sheets import sync_workspace_to_sheet, SheetsSyncError

settings_bp = Blueprint("settings", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


def _workspace_tasks():
    workspace_id = _current_workspace_id()
    board_ids = [b.id for b in Board.query.filter_by(workspace_id=workspace_id).all()]
    return Task.query.filter(Task.board_id.in_(board_ids)).all() if board_ids else []


@settings_bp.route("/settings")
@login_required
def view_settings():
    return render_template("settings.html")


@settings_bp.route("/api/settings/theme", methods=["POST"])
@login_required
def set_theme():
    theme = request.json.get("theme")
    if theme not in ("light", "dark"):
        return jsonify({"error": "Invalid theme"}), 400

    current_user.theme = theme
    db.session.commit()
    return jsonify({"theme": theme})


@settings_bp.route("/export/csv")
@login_required
def export_csv():
    tasks = _workspace_tasks()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Title", "Description", "Priority", "Status", "Due Date",
        "Tags", "Owner", "Created By", "Created Date", "Last Updated"
    ])

    for t in tasks:
        writer.writerow([
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

    csv_data = buffer.getvalue()
    buffer.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=kanplan_tasks.csv"},
    )


@settings_bp.route("/api/sheets/sync", methods=["POST"])
@login_required
def sync_sheets():
    workspace_id = _current_workspace_id()
    workspace = Workspace.query.get(workspace_id)
    tasks = _workspace_tasks()

    try:
        sheet_url = sync_workspace_to_sheet(
            user=current_user,
            workspace=workspace,
            tasks=tasks,
            client_id=current_app.config["GOOGLE_CLIENT_ID"],
            client_secret=current_app.config["GOOGLE_CLIENT_SECRET"],
        )
        return jsonify({"sheet_url": sheet_url})
    except SheetsSyncError as e:
        return jsonify({"error": str(e)}), 400
