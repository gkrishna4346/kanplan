from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from database.models import db, Board, Task, ActivityLog, WorkspaceMember

board_bp = Blueprint("board", __name__)


def _current_membership():
    return WorkspaceMember.query.filter_by(user_id=current_user.id).first()


def _current_workspace_id():
    membership = _current_membership()
    return membership.workspace_id if membership else None


def _current_role():
    membership = _current_membership()
    return membership.role if membership else "member"


@board_bp.route("/board")
@login_required
def view_board():
    workspace_id = _current_workspace_id()
    board = Board.query.filter_by(workspace_id=workspace_id).first()
    tasks = (
        Task.query
        .filter_by(board_id=board.id, archived=False)
        .order_by(Task.position)
        .all()
    )

    columns = {col: [] for col in Board.DEFAULT_COLUMNS}
    for t in tasks:
        columns.setdefault(t.status, []).append(t)

    members = (
        WorkspaceMember.query
        .filter_by(workspace_id=workspace_id)
        .join(WorkspaceMember.user)
        .all()
    )

    archived_count = Task.query.filter_by(board_id=board.id, archived=True).count()

    return render_template(
        "board.html",
        board=board,
        columns=columns,
        members=members,
        current_role=_current_role(),
        archived_count=archived_count,
    )


@board_bp.route("/board/archived")
@login_required
def view_archived():
    workspace_id = _current_workspace_id()
    board = Board.query.filter_by(workspace_id=workspace_id).first()
    tasks = (
        Task.query
        .filter_by(board_id=board.id, archived=True)
        .order_by(Task.updated_at.desc())
        .all()
    )

    return render_template(
        "archived.html",
        board=board,
        tasks=tasks,
        current_role=_current_role(),
    )


@board_bp.route("/api/tasks/<task_id>/restore", methods=["PATCH"])
@login_required
def restore_task(task_id):
    """Un-archives a task, putting it back on the board."""
    task = Task.query.get_or_404(task_id)
    role = _current_role()

    if not task.can_edit(current_user.id, role):
        return jsonify({"error": "You can only restore tasks you created or are assigned to."}), 403

    task.archived = False
    db.session.add(ActivityLog(task_id=task.id, user_id=current_user.id, action="restored"))
    db.session.commit()

    return jsonify({"archived": False})


@board_bp.route("/api/tasks", methods=["POST"])
@login_required
def create_task():
    data = request.json
    workspace_id = _current_workspace_id()
    board = Board.query.filter_by(workspace_id=workspace_id).first()

    task = Task(
        board_id=board.id,
        title=data["title"],
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
        status=data.get("status", "Backlog"),
        tags=data.get("tags", ""),
        assignee_id=data.get("assignee_id") or None,
        created_by_id=current_user.id,
    )
    if data.get("due_date"):
        task.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()

    db.session.add(task)
    db.session.flush()

    db.session.add(ActivityLog(task_id=task.id, user_id=current_user.id, action="created"))
    db.session.commit()

    return jsonify(task.to_dict(current_user.id, _current_role())), 201


@board_bp.route("/api/tasks/<task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    role = _current_role()

    if not task.can_edit(current_user.id, role):
        return jsonify({"error": "You can only edit tasks you created or are assigned to."}), 403

    data = request.json

    for field in ["title", "description", "priority", "status", "tags"]:
        if field in data:
            setattr(task, field, data[field])

    if "due_date" in data:
        task.due_date = (
            datetime.strptime(data["due_date"], "%Y-%m-%d").date()
            if data["due_date"] else None
        )
    if "assignee_id" in data:
        task.assignee_id = data["assignee_id"] or None

    db.session.add(ActivityLog(task_id=task.id, user_id=current_user.id, action="edited"))
    db.session.commit()

    return jsonify(task.to_dict(current_user.id, role))


@board_bp.route("/api/tasks/<task_id>/move", methods=["PATCH"])
@login_required
def move_task(task_id):
    """Called by the drag-and-drop JS when a card changes column/position."""
    task = Task.query.get_or_404(task_id)
    role = _current_role()

    if not task.can_edit(current_user.id, role):
        return jsonify({"error": "You can only move tasks you created or are assigned to."}), 403

    data = request.json

    task.status = data["status"]
    task.position = data.get("position", 0)

    db.session.add(ActivityLog(
        task_id=task.id, user_id=current_user.id,
        action="moved", detail=f"-> {task.status}"
    ))
    db.session.commit()

    return jsonify(task.to_dict(current_user.id, role))


@board_bp.route("/api/tasks/<task_id>/activity")
@login_required
def task_activity(task_id):
    logs = (
        ActivityLog.query
        .filter_by(task_id=task_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify([
        {
            "action": log.action,
            "detail": log.detail,
            "user_name": log.user.name if log.user else "Someone",
            "created_at": log.created_at.strftime("%b %-d, %I:%M %p"),
        }
        for log in logs
    ])


@board_bp.route("/api/tasks/<task_id>/archive", methods=["PATCH"])
@login_required
def archive_task(task_id):
    """Soft-delete: hides the task from the board but keeps it in the database.
    Available to the task's creator/assignee, or an admin."""
    task = Task.query.get_or_404(task_id)
    role = _current_role()

    if not task.can_edit(current_user.id, role):
        return jsonify({"error": "You can only archive tasks you created or are assigned to."}), 403

    task.archived = True
    db.session.add(ActivityLog(task_id=task.id, user_id=current_user.id, action="archived"))
    db.session.commit()

    return jsonify({"archived": True})


@board_bp.route("/api/tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    """Permanent delete. Admin only -- everyone else should use Archive instead."""
    role = _current_role()
    if role != "admin":
        return jsonify({"error": "Only a workspace admin can permanently delete a task."}), 403

    task = Task.query.get_or_404(task_id)
    db.session.add(ActivityLog(task_id=task.id, user_id=current_user.id, action="deleted"))
    db.session.delete(task)
    db.session.commit()
    return "", 204
