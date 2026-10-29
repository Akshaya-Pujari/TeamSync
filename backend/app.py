
import os

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

    if db.session.get(Channel, channel_id):
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

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
