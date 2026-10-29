
import os
import secrets

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from dotenv import load_dotenv
from sqlalchemy.engine import URL
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Channel, Message
from flask_socketio import SocketIO, join_room
from models import Workspace, WorkspaceMember

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

database_url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5433")),
    database=os.getenv("DB_NAME", "teamsync_db")
)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

CORS(
    app,
    resources={r"/api/*": {
        "origins": "http://localhost:5173"
    }},
    supports_credentials=True
)

db.init_app(app)

socketio = SocketIO(app, cors_allowed_origins="http://localhost:5173")


@socketio.on("join_channel")
def handle_join(data):
    if not current_user.is_authenticated:
        return

    try:
        channel_id = int(data["channel_id"])
    except (KeyError, TypeError, ValueError):
        return

    channel = db.session.get(Channel, channel_id)

    if (
        channel
        and channel.workspace_id is not None
        and is_workspace_member(
            channel.workspace_id, current_user.id
        )
    ):
        join_room(f"channel_{channel_id}")

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Authentication required"}), 401



@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not email or len(password) < 12:
        return jsonify({
            "error": "Username, email and a password of at least 12 characters are required"
        }), 400

    if "@" not in email:
        return jsonify({"error": "Invalid email"}), 400

    existing = db.session.execute(
        db.select(User).where(
            (User.username == username) | (User.email == email)
        )
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Username or email already exists"}), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password)
    )

    db.session.add(user)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Could not create account"}), 409

    login_user(user)

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email
    }), 201

@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    user = db.session.execute(
        db.select(User).filter_by(email=email)
    ).scalar_one_or_none()

    if not user or not user.password_hash or not check_password_hash(
        user.password_hash, password
    ):
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(user)

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email
    })


@app.post("/api/auth/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})


@app.get("/api/auth/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"user": None})

    return jsonify({
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email
        }
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/channels")
@login_required
def get_channels():
    channels = db.session.execute(
        db.select(Channel).order_by(Channel.id)
    ).scalars().all()

    return jsonify([
        {"id": c.id, "name": c.name} for c in channels
    ])


@app.post("/api/channels")
@login_required
def create_channel():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name or len(name) > 100:
        return jsonify({"error": "Invalid channel name"}), 400

    existing = db.session.execute(
        db.select(Channel).filter_by(name=name)
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Channel already exists"}), 409

    channel = Channel(name=name)
    db.session.add(channel)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Could not create channel"}), 409

    return jsonify({
        "id": channel.id,
        "name": channel.name
    }), 201


@app.get("/api/channels/<int:channel_id>/messages")
@login_required
def get_messages(channel_id):
    channel = db.session.get(Channel, channel_id)

    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    messages = db.session.execute(
        db.select(Message)
        .filter_by(channel_id=channel_id)
        .order_by(Message.created_at, Message.id)
    ).scalars().all()

    return jsonify([
        {
            "id": m.id,
            "content": m.content,
            "username": m.user.username,
            "user_id": m.user_id,
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ])



@app.post("/api/channels/<int:channel_id>/messages")
@login_required
def send_message(channel_id):
    channel = db.session.get(Channel, channel_id)

    if not channel:
        return jsonify({"error": "Channel not found"}), 404

        if (
        channel.workspace_id is None
        or not is_workspace_member(
            channel.workspace_id, current_user.id
        )
    ):
         return jsonify({"error": "Access denied"}), 403
    

    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()

    if not content or len(content) > 5000:
        return jsonify({"error": "Invalid message"}), 400

    message = Message(
        content=content,
        user_id=current_user.id,
        channel_id=channel_id
    )

    db.session.add(message)
    db.session.commit()

    message_data = {
        "id": message.id,
        "content": message.content,
        "username": current_user.username,
        "user_id": current_user.id,
        "created_at": message.created_at.isoformat(),
        "channel_id": channel_id
    }

    # Broadcast the new message to everyone in this channel.
    socketio.emit(
        "new_message",
        message_data,
        to=f"channel_{channel_id}"
    )

    return jsonify(message_data), 201


def is_workspace_member(workspace_id, user_id):
    return db.session.get(
        WorkspaceMember, (workspace_id, user_id)
    ) is not None


@app.post("/api/workspaces")
@login_required
def create_workspace():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name or len(name) > 100:
        return jsonify({"error": "Invalid workspace name"}), 400

    workspace = Workspace(
        name=name,
        owner_id=current_user.id,
        invite_code=secrets.token_urlsafe(18)
    )

    db.session.add(workspace)
    db.session.flush()

    db.session.add(WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="owner"
    ))

    db.session.add(Channel(
        name="general",
        workspace_id=workspace.id
    ))

    db.session.commit()

    return jsonify({
        "id": workspace.id,
        "name": workspace.name,
        "invite_code": workspace.invite_code
    }), 201


@app.post("/api/workspaces/join")
@login_required
def join_workspace():
    data = request.get_json(silent=True) or {}
    code = str(data.get("invite_code", "")).strip()

    workspace = db.session.execute(
        db.select(Workspace).filter_by(invite_code=code)
    ).scalar_one_or_none()

    if not workspace:
        return jsonify({"error": "Invalid invite code"}), 404

    if not is_workspace_member(workspace.id, current_user.id):
        db.session.add(WorkspaceMember(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role="member"
        ))
        db.session.commit()

    return jsonify({
        "id": workspace.id,
        "name": workspace.name
    })


@app.get("/api/workspaces/<int:workspace_id>/invite")
@login_required
def get_invite_code(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace:
        return jsonify({"error": "Workspace not found"}), 404

    membership = db.session.get(
        WorkspaceMember, (workspace_id, current_user.id)
    )

    if not membership or membership.role != "owner":
        return jsonify({"error": "Owner access required"}), 403

    return jsonify({"invite_code": workspace.invite_code})


@app.get("/api/workspaces/<int:workspace_id>/channels")
@login_required
def get_workspace_channels(workspace_id):
    if not is_workspace_member(workspace_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    channels = db.session.execute(
        db.select(Channel)
        .filter_by(workspace_id=workspace_id)
        .order_by(Channel.id)
    ).scalars().all()

    return jsonify([
        {"id": c.id, "name": c.name}
        for c in channels
    ])


@app.post("/api/workspaces/<int:workspace_id>/channels")
@login_required
def create_workspace_channel(workspace_id):
    if not is_workspace_member(workspace_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name or len(name) > 100:
        return jsonify({"error": "Invalid channel name"}), 400

    existing = db.session.execute(
        db.select(Channel).filter_by(
            workspace_id=workspace_id,
            name=name
        )
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Channel already exists"}), 409

    channel = Channel(
        name=name,
        workspace_id=workspace_id
    )

    db.session.add(channel)
    db.session.commit()

    return jsonify({
        "id": channel.id,
        "name": channel.name
    }), 201

@app.get("/api/workspaces")
@login_required
def get_workspaces():
    workspaces = db.session.execute(
        db.select(Workspace)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == current_user.id)
        .order_by(Workspace.id)
    ).scalars().all()
    
    return jsonify([
        {
            "id": w.id,
            "name": w.name,
            "owner_id": w.owner_id,
            "role": db.session.get(
                WorkspaceMember, (w.id, current_user.id)
            ).role
        }
        for w in workspaces
    ])

# Rename workspace - owner only
@app.patch("/api/workspaces/<int:workspace_id>")
@login_required
def rename_workspace(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace:
        return jsonify({"error": "Workspace not found"}), 404

    membership = db.session.get(
        WorkspaceMember, (workspace_id, current_user.id)
    )

    if not membership or membership.role != "owner":
        return jsonify({"error": "Owner access required"}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name or len(name) > 100:
        return jsonify({"error": "Invalid workspace name"}), 400

    workspace.name = name
    db.session.commit()

    return jsonify({"id": workspace.id, "name": workspace.name})


# Transfer ownership - owner only
@app.post("/api/workspaces/<int:workspace_id>/transfer-ownership")
@login_required
def transfer_ownership(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace:
        return jsonify({"error": "Workspace not found"}), 404

    if workspace.owner_id != current_user.id:
        return jsonify({"error": "Owner access required"}), 403

    data = request.get_json(silent=True) or {}

    try:
        new_owner_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid user ID required"}), 400

    if new_owner_id == current_user.id:
        return jsonify({"error": "Already the owner"}), 400

    new_owner = db.session.get(
        WorkspaceMember, (workspace_id, new_owner_id)
    )

    if not new_owner:
        return jsonify({
            "error": "New owner must be a workspace member"
        }), 400

    old_owner = db.session.get(
        WorkspaceMember, (workspace_id, current_user.id)
    )

    if not old_owner:
        return jsonify({"error": "Owner membership missing"}), 409

    new_owner.role = "owner"
    old_owner.role = "member"
    workspace.owner_id = new_owner_id

    db.session.commit()

    return jsonify({"message": "Ownership transferred"})


# Leave workspace - members only
@app.post("/api/workspaces/<int:workspace_id>/leave")
@login_required
def leave_workspace(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace:
        return jsonify({"error": "Workspace not found"}), 404

    membership = db.session.get(
        WorkspaceMember, (workspace_id, current_user.id)
    )

    if not membership:
        return jsonify({"error": "Not a workspace member"}), 403

    if workspace.owner_id == current_user.id:
        return jsonify({
            "error": "Transfer ownership before leaving"
        }), 400

    db.session.delete(membership)
    db.session.commit()

    return jsonify({"message": "Left workspace successfully"})


@app.patch("/api/channels/<int:channel_id>")
@login_required
def rename_channel(channel_id):
    channel = db.session.get(Channel, channel_id)

    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    workspace = db.session.get(Workspace, channel.workspace_id)

    if not workspace or workspace.owner_id != current_user.id:
        return jsonify({"error": "Owner access required"}), 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name or len(name) > 100:
        return jsonify({"error": "Invalid channel name"}), 400

    existing = db.session.execute(
        db.select(Channel).where(
            Channel.workspace_id == channel.workspace_id,
            Channel.name == name,
            Channel.id != channel.id
        )
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Channel name already exists"}), 409

    channel.name = name
    db.session.commit()

    return jsonify({"id": channel.id, "name": channel.name})


@app.delete("/api/channels/<int:channel_id>")
@login_required
def delete_channel(channel_id):
    channel = db.session.get(Channel, channel_id)

    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    workspace = db.session.get(Workspace, channel.workspace_id)

    if not workspace or workspace.owner_id != current_user.id:
        return jsonify({"error": "Owner access required"}), 403

    # Delete messages before deleting their channel.
    db.session.execute(
        db.delete(Message).where(Message.channel_id == channel.id)
    )

    db.session.delete(channel)
    db.session.commit()

    return jsonify({"message": "Channel deleted"})

@app.patch("/api/messages/<int:message_id>")
@login_required
def edit_message(message_id):
    msg = db.session.get(Message, message_id)

    if not msg:
        return jsonify({"error": "Message not found"}), 404

    channel = db.session.get(Channel, msg.channel_id)
    if (
        not channel
        or not is_workspace_member(channel.workspace_id, current_user.id)
    ):
        return jsonify({"error": "Access denied"}), 403

    if msg.user_id != current_user.id:
        return jsonify({"error": "Cannot edit another user's message"}), 403

    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()

    if not content or len(content) > 5000:
        return jsonify({"error": "Invalid message"}), 400

    msg.content = content
    db.session.commit()

    result = {
        "id": msg.id,
        "content": msg.content,
        "channel_id": msg.channel_id
    }

    socketio.emit(
        "message_updated",
        result,
        to=f"channel_{msg.channel_id}"
    )

    return jsonify(result)


@app.delete("/api/messages/<int:message_id>")
@login_required
def delete_message(message_id):
    msg = db.session.get(Message, message_id)

    if not msg:
        return jsonify({"error": "Message not found"}), 404

    channel = db.session.get(Channel, msg.channel_id)
    if (
        not channel
        or not is_workspace_member(channel.workspace_id, current_user.id)
    ):
        return jsonify({"error": "Access denied"}), 403

    if msg.user_id != current_user.id:
        return jsonify({"error": "Cannot delete another user's message"}), 403

    result = {
        "id": msg.id,
        "channel_id": msg.channel_id
    }

    db.session.delete(msg)
    db.session.commit()

    socketio.emit(
        "message_deleted",
        result,
        to=f"channel_{result['channel_id']}"
    )

    return jsonify({"message": "Deleted"})

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
