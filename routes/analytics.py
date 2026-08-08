from datetime import date, timedelta
from collections import OrderedDict

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from database.models import db, Task, Board, WorkspaceMember

analytics_bp = Blueprint("analytics", __name__)


def _current_workspace_id():
    membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
    return membership.workspace_id if membership else None


def _workspace_tasks(workspace_id):
    board_ids = [b.id for b in Board.query.filter_by(workspace_id=workspace_id).all()]
    return Task.query.filter(Task.board_id.in_(board_ids)).all() if board_ids else []


@analytics_bp.route("/analytics")
@login_required
def view_analytics():
    workspace_id = _current_workspace_id()
    tasks = _workspace_tasks(workspace_id)

    # ---------- Status distribution ----------
    status_counts = OrderedDict()
    for status in Board.DEFAULT_COLUMNS:
        status_counts[status] = 0
    for t in tasks:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1

    # ---------- Weekly completed (last 7 days, by day) ----------
    today = date.today()
    weekly_labels = []
    weekly_counts = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        weekly_labels.append(day.strftime("%a"))
        count = sum(
            1 for t in tasks
            if t.status == "Completed" and t.updated_at and t.updated_at.date() == day
        )
        weekly_counts.append(count)

    # ---------- Monthly completed (last 6 months, by month) ----------
    monthly_labels = []
    monthly_counts = []
    year, month = today.year, today.month
    months = []
    for _ in range(6):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()

    for (y, m) in months:
        monthly_labels.append(date(y, m, 1).strftime("%b"))
        count = sum(
            1 for t in tasks
            if t.status == "Completed" and t.updated_at
            and t.updated_at.year == y and t.updated_at.month == m
        )
        monthly_counts.append(count)

    # ---------- Per-person breakdown ----------
    members = (
        WorkspaceMember.query
        .filter_by(workspace_id=workspace_id)
        .join(WorkspaceMember.user)
        .all()
    )
    person_stats = []
    for m in members:
        person_tasks = [t for t in tasks if t.assignee_id == m.user_id]
        p_total = len(person_tasks)
        p_completed = sum(1 for t in person_tasks if t.status == "Completed")
        person_stats.append({
            "name": m.user.name,
            "initials": m.user.initials(),
            "total": p_total,
            "completed": p_completed,
            "productivity": round((p_completed / p_total) * 100) if p_total else 0,
        })
    unassigned_count = sum(1 for t in tasks if not t.assignee_id)
    if unassigned_count:
        unassigned_completed = sum(1 for t in tasks if not t.assignee_id and t.status == "Completed")
        person_stats.append({
            "name": "Unassigned",
            "initials": "—",
            "total": unassigned_count,
            "completed": unassigned_completed,
            "productivity": round((unassigned_completed / unassigned_count) * 100) if unassigned_count else 0,
        })
    person_stats.sort(key=lambda p: p["total"], reverse=True)

    total = len(tasks)
    completed_total = status_counts.get("Completed", 0)
    overall_productivity = round((completed_total / total) * 100) if total else 0

    return render_template(
        "analytics.html",
        status_labels=list(status_counts.keys()),
        status_values=list(status_counts.values()),
        weekly_labels=weekly_labels,
        weekly_counts=weekly_counts,
        monthly_labels=monthly_labels,
        monthly_counts=monthly_counts,
        person_stats=person_stats,
        overall_productivity=overall_productivity,
        total_tasks=total,
    )
