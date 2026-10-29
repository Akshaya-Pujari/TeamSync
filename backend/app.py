
import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import URL

from models import db, User, Channel, Message

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}})

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5433")),
    database=os.getenv("DB_NAME", "teamsync_db")
)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/db-test")
def db_test():
    with db.engine.connect() as connection:
        name = connection.execute(
            text("SELECT current_database()")
        ).scalar()

    return jsonify({"status": "connected", "database": name})


@app.route("/api/channels", methods=["GET"])
def get_channels():
    channels = db.session.execute(
        db.select(Channel).order_by(Channel.id)
    ).scalars().all()

    return jsonify([
        {"id": c.id, "name": c.name} for c in channels
    ])


@app.route("/api/channels", methods=["POST"])
def create_channel():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name:
        return jsonify({"error": "Channel name required"}), 400

    existing = db.session.execute(
        db.select(Channel).filter_by(name=name)
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Channel already exists"}), 409

    channel = Channel(name=name)
    db.session.add(channel)
    db.session.commit()

    return jsonify({
        "id": channel.id,
        "name": channel.name
    }), 201


@app.route("/api/channels/<int:channel_id>/messages", methods=["GET"])
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
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ])


@app.route("/api/channels/<int:channel_id>/messages", methods=["POST"])
def send_message(channel_id):
    channel = db.session.get(Channel, channel_id)

    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()

    if not content:
        return jsonify({"error": "Message cannot be empty"}), 400

    user = db.session.execute(
        db.select(User).filter_by(username="Demo User")
    ).scalar_one()

    message = Message(
        content=content,
        user_id=user.id,
        channel_id=channel_id
    )

    db.session.add(message)
    db.session.commit()

    return jsonify({
        "id": message.id,
        "content": message.content,
        "username": user.username,
        "created_at": message.created_at.isoformat()
    }), 201


def initialize_database():
    with app.app_context():
        db.create_all()

        if not db.session.execute(
            db.select(User).filter_by(username="Demo User")
        ).scalar_one_or_none():
            db.session.add(User(username="Demo User"))

        if not db.session.execute(
            db.select(Channel).filter_by(name="general")
        ).scalar_one_or_none():
            db.session.add(Channel(name="general"))

        db.session.commit()


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True, port=5000)
