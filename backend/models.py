
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)
    password_hash = db.Column(db.String(255))


class Workspace(db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(
        db.String(32), unique=True, nullable=False
    )
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )


class WorkspaceMember(db.Model):
    __tablename__ = "workspace_members"

    workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspaces.id"),
        primary_key=True
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        primary_key=True
    )
    role = db.Column(
        db.String(20), nullable=False, default="member"
    )

class Channel(db.Model):
    __tablename__ = "channels"

    workspace_id = db.Column(
    db.Integer,
    db.ForeignKey("workspaces.id"),
    nullable=True
)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    channel_id = db.Column(
        db.Integer, db.ForeignKey("channels.id"), nullable=False
    )

    user = db.relationship("User")
