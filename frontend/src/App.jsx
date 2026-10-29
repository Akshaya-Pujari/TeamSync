
import { useEffect, useState } from "react";
import { Hash, Plus, Send, Users } from "lucide-react";
import "./App.css";

const API = "http://127.0.0.1:5000/api";

export default function App() {
  const [channels, setChannels] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/channels`)
      .then((res) => res.json())
      .then((data) => {
        setChannels(data);
        if (data.length) setSelected(data[0]);
      })
      .catch(() => setError("Cannot connect to backend"));
  }, []);

  useEffect(() => {
    if (!selected) return;

    fetch(`${API}/channels/${selected.id}/messages`)
      .then((res) => res.json())
      .then(setMessages)
      .catch(() => setError("Could not load messages"));
  }, [selected]);

  async function sendMessage(e) {
    e.preventDefault();
    if (!message.trim() || !selected) return;

    try {
      const res = await fetch(
        `${API}/channels/${selected.id}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: message }),
        }
      );

      if (!res.ok) throw new Error("Message failed");

      const saved = await res.json();
      setMessages((prev) => [...prev, saved]);
      setMessage("");
      setError("");
    } catch {
      setError("Failed to send message");
    }
  }

  async function addChannel() {
    const name = prompt("Enter channel name:");
    if (!name?.trim()) return;

    try {
      const res = await fetch(`${API}/channels`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });

      if (!res.ok) throw new Error();

      const channel = await res.json();
      setChannels((prev) => [...prev, channel]);
      setSelected(channel);
      setError("");
    } catch {
      setError("Could not create channel");
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">T</div>
          <div>
            <h2>TeamSync</h2>
            <span>Team Workspace</span>
          </div>
        </div>

        <div className="workspace">
          <Users size={18} />
          <span>My Workspace</span>
        </div>

        <div className="channel-heading">
          <span>CHANNELS</span>
          <button onClick={addChannel} title="Add channel">
            <Plus size={18} />
          </button>
        </div>

        <nav>
          {channels.map((channel) => (
            <button
              key={channel.id}
              className={
                selected?.id === channel.id
                  ? "channel active"
                  : "channel"
              }
              onClick={() => setSelected(channel)}
            >
              <Hash size={17} />
              {channel.name}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="avatar">D</div>
          <div>
            <strong>Demo User</strong>
            <small>Online</small>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h2>
              <Hash size={23} />
              {selected?.name || "Select a channel"}
            </h2>
            <p>Team conversations, all in one place.</p>
          </div>
          <span className="demo-tag">TeamSync MVP</span>
        </header>

        <section className="messages">
          {messages.length === 0 && (
            <div className="empty">
              <Hash size={38} />
              <h3>Start the conversation</h3>
              <p>Send the first message in this channel.</p>
            </div>
          )}

          {messages.map((m) => (
            <div className="message" key={m.id}>
              <div className="avatar">{m.username[0]}</div>
              <div className="message-body">
                <div className="message-meta">
                  <strong>{m.username}</strong>
                  <time>
                    {new Date(m.created_at).toLocaleTimeString(
                      [], { hour: "2-digit", minute: "2-digit" }
                    )}
                  </time>
                </div>
                <p>{m.content}</p>
              </div>
            </div>
          ))}
        </section>

        <div className="composer-area">
          {error && <p className="error">{error}</p>}
          <form className="composer" onSubmit={sendMessage}>
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={
                selected
                  ? `Message #${selected.name}`
                  : "Select a channel"
              }
              disabled={!selected}
            />
            <button disabled={!selected || !message.trim()}>
              <Send size={19} />
            </button>
          </form>
          <p className="hint">Messages are saved in PostgreSQL.</p>
        </div>
      </main>
    </div>
  );
}
