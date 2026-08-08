import uuid
from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


def gen_uuid():
    return str(uuid.uuid4())


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    google_sub = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    avatar_url = db.Column(db.String(500))
    theme = db.Column(db.String(10), default="light")  # light | dark
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Stored so we can call the Google Sheets API later (e.g. "Sync Now"),
    # not just during the login request itself.
    google_access_token = db.Column(db.Text, nullable=True)
    google_refresh_token = db.Column(db.Text, nullable=True)
    google_token_expiry = db.Column(db.DateTime, nullable=True)

    memberships = db.relationship("WorkspaceMember", back_populates="user")

    def initials(self):
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper() if parts else "?"


class Workspace(db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Populated the first time someone runs "Sync Now" -- reused on later syncs
    # so we update the same sheet instead of creating a new one each time.
    sheet_id = db.Column(db.String(255), nullable=True)
    sheet_url = db.Column(db.String(500), nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True)

    members = db.relationship("WorkspaceMember", back_populates="workspace")
    boards = db.relationship("Board", back_populates="workspace")


class WorkspaceMember(db.Model):
    """Join table: who belongs to which workspace, and their role."""
    __tablename__ = "workspace_members"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default="member")  # admin | member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    workspace = db.relationship("Workspace", back_populates="members")
    user = db.relationship("User", back_populates="memberships")

    __table_args__ = (
        db.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
    )


class Board(db.Model):
    __tablename__ = "boards"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    workspace = db.relationship("Workspace", back_populates="boards")
    tasks = db.relationship("Task", back_populates="board", cascade="all, delete-orphan")

    DEFAULT_COLUMNS = ["Backlog", "To Do", "In Progress", "Review", "Completed"]


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    board_id = db.Column(db.String(36), db.ForeignKey("boards.id"), nullable=False)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default="")
    priority = db.Column(db.String(10), default="medium")  # low | medium | high
    status = db.Column(db.String(30), default="Backlog")
    due_date = db.Column(db.Date, nullable=True)
    tags = db.Column(db.String(255), default="")  # comma-separated for simplicity in v1

    assignee_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    position = db.Column(db.Integer, default=0)  # order within its column
    archived = db.Column(db.Boolean, default=False)  # soft-delete: hidden from board, kept for audit

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    board = db.relationship("Board", back_populates="tasks")
    assignee = db.relationship("User", foreign_keys=[assignee_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    def is_overdue(self):
        return bool(
            self.due_date
            and self.due_date < date.today()
            and self.status != "Completed"
        )

    def can_edit(self, user_id, role):
        """Admins can edit anything. Everyone else can only edit tasks
        they created or are currently assigned to."""
        return role == "admin" or user_id == self.created_by_id or user_id == self.assignee_id

    def to_dict(self, viewer_id=None, viewer_role=None):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()],
            "assignee": self.assignee.name if self.assignee else None,
            "assignee_initials": self.assignee.initials() if self.assignee else None,
            "created_by_id": self.created_by_id,
            "is_overdue": self.is_overdue(),
            "can_edit": self.can_edit(viewer_id, viewer_role) if viewer_id else None,
        }


class Invite(db.Model):
    """A pending invite to a workspace, before the person has ever logged in."""
    __tablename__ = "invites"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    invited_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default="member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    workspace = db.relationship("Workspace")
    invited_by = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("workspace_id", "email", name="uq_workspace_invite_email"),
    )


class ActivityLog(db.Model):
    """Lightweight audit trail - who did what, on which task."""
    __tablename__ = "activity_log"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    task_id = db.Column(db.String(36), db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # created | edited | moved | deleted
    detail = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")
