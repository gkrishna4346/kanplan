from datetime import date
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from database.models import db, Task, Board, WorkspaceMember

dashboard_bp = Blueprint("dashboard", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


@dashboard_bp.route("/")
@login_required
def index():
    workspace_id = _current_workspace_id()
    board_ids = [b.id for b in Board.query.filter_by(workspace_id=workspace_id).all()]

    tasks = Task.query.filter(Task.board_id.in_(board_ids)).all() if board_ids else []

    total = len(tasks)
    pending = sum(1 for t in tasks if t.status == "Backlog")
    in_progress = sum(1 for t in tasks if t.status == "In Progress")
    completed = sum(1 for t in tasks if t.status == "Completed")
    overdue = sum(1 for t in tasks if t.is_overdue())
    today_tasks = sum(1 for t in tasks if t.due_date == date.today())
    productivity = round((completed / total) * 100) if total else 0

    stats = {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "overdue": overdue,
        "today": today_tasks,
        "productivity": productivity,
    }

    return render_template("dashboard.html", stats=stats)
