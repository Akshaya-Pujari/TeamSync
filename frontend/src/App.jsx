
import { useEffect, useRef, useState } from "react";
import { Hash, Plus, Send, Users } from "lucide-react";
import { io } from "socket.io-client";
import Auth from "./Auth";
import "./App.css";

const API = "/api";

export default function App() {
  const [channels, setChannels] = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);

  const selectedRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Check authentication once.
  useEffect(() => {
    let active = true;

    fetch(`${API}/auth/me`, {
      credentials: "include",
    })
      .then((res) => {
        if (!res.ok) throw new Error("Authentication check failed");
        return res.json();
      })
      .then((data) => {
        if (active) setUser(data.user);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setCheckingAuth(false);
      });

    return () => {
      active = false;
    };
  }, []);

  // Load channels and restore the last selected channel.
  useEffect(() => {
    if (!user) return;

    let active = true;

    async function loadChannels() {
      try {
        const res = await fetch(`${API}/channels`, {
          credentials: "include",
        });

        if (!res.ok) throw new Error("Failed to load channels");

        const data = await res.json();
        if (!active) return;

        setChannels(data);

        const savedId = Number(
          localStorage.getItem(`teamsync_channel_${user.id}`)
        );

        const savedChannel = data.find(
          (channel) => channel.id === savedId
        );

        setSelected(savedChannel || data[0] || null);
        setError("");
      } catch {
        if (active) setError("Cannot connect to backend");
      }
    }

    loadChannels();

    return () => {
      active = false;
    };
  }, [user]);

  // Remember the current channel.
  useEffect(() => {
    selectedRef.current = selected;

    if (user && selected) {
      localStorage.setItem(
        `teamsync_channel_${user.id}`,
        String(selected.id)
      );
    }
  }, [selected, user]);

  // Load messages whenever the channel changes.
  useEffect(() => {
    if (!user || !selected) return;

    let active = true;
    const channelId = selected.id;

    setMessages([]);

    async function loadMessages() {
      try {
        const res = await fetch(
          `${API}/channels/${channelId}/messages`,
          { credentials: "include" }
        );

        if (!res.ok) throw new Error("Failed to load messages");

        const data = await res.json();

        if (active) {
          setMessages((prev) => {
            const merged = new Map();

            data.forEach((m) => merged.set(m.id, m));
            prev.forEach((m) => merged.set(m.id, m));

            return [...merged.values()].sort(
              (a, b) => a.id - b.id
            );
          });

          setError("");
        }
      } catch {
        if (active) setError("Could not load messages");
      }
    }

    loadMessages();

    return () => {
      active = false;
    };
  }, [selected, user]);

  // Real-time Socket.IO connection.
  useEffect(() => {
    if (!user || !selected) return;

    const channelId = selected.id;

    const socket = io("/", {
      path: "/socket.io",
      transports: ["polling", "websocket"],
      reconnection: true,
      reconnectionAttempts: Infinity,
    });

    socket.on("connect", () => {
      console.log("Socket connected:", socket.id);
      setConnected(true);

      socket.emit("join_channel", {
        channel_id: channelId,
      });

      // Refresh messages after reconnecting.
      fetch(`${API}/channels/${channelId}/messages`, {
        credentials: "include",
      })
        .then((res) => {
          if (!res.ok) throw new Error("Refresh failed");
          return res.json();
        })
        .then((data) => {
          if (selectedRef.current?.id !== channelId) return;

          setMessages((prev) => {
            const merged = new Map();

            data.forEach((m) => merged.set(m.id, m));
            prev.forEach((m) => merged.set(m.id, m));

            return [...merged.values()].sort(
              (a, b) => a.id - b.id
            );
          });
        })
        .catch((err) => console.error(err));
    });

    socket.on("new_message", (incoming) => {
      if (incoming.channel_id !== channelId) return;

      setMessages((prev) => {
        if (prev.some((m) => m.id === incoming.id)) {
          return prev;
        }

        return [...prev, incoming].sort(
          (a, b) => a.id - b.id
        );
      });
    });

    socket.on("disconnect", () => {
      setConnected(false);
    });

    socket.on("connect_error", (err) => {
      console.error("Socket connection failed:", err.message);
      setConnected(false);
    });

    return () => {
      socket.disconnect();
      setConnected(false);
    };
  }, [user, selected]);

  // Scroll to the newest message.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  async function sendMessage(e) {
    e.preventDefault();

    if (!message.trim() || !selected || sending) return;

    const content = message.trim();
    const channelId = selected.id;

    setSending(true);

    try {
      const res = await fetch(
        `${API}/channels/${channelId}/messages`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content }),
        }
      );

      if (!res.ok) throw new Error("Message failed");

      const saved = await res.json();

      // Immediate display, even if Socket.IO is disconnected.
      if (selectedRef.current?.id === channelId) {
        setMessages((prev) => {
          if (prev.some((m) => m.id === saved.id)) return prev;
          return [...prev, saved].sort((a, b) => a.id - b.id);
        });
      }

      setMessage("");
      setError("");
    } catch {
      setError("Failed to send message");
    } finally {
      setSending(false);
    }
  }

  async function addChannel() {
    const name = window.prompt("Enter channel name:");
    if (!name?.trim()) return;

    try {
      const res = await fetch(`${API}/channels`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: name.trim() }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Could not create channel");
      }

      setChannels((prev) => [...prev, data]);
      setSelected(data);
      setMessage("");
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function logout() {
    try {
      const res = await fetch(`${API}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });

      if (!res.ok) throw new Error("Logout failed");

      setUser(null);
      setChannels([]);
      setSelected(null);
      setMessages([]);
      setMessage("");
      setError("");
    } catch {
      setError("Could not log out. Please try again.");
    }
  }

  if (checkingAuth) {
    return <div className="auth-page">Loading TeamSync...</div>;
  }

  if (!user) {
    return <Auth onLogin={setUser} />;
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
          <button
            onClick={addChannel}
            title="Add channel"
            aria-label="Add channel"
          >
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
              onClick={() => {
                setSelected(channel);
                setMessage("");
                setError("");
              }}
            >
              <Hash size={17} />
              {channel.name}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="avatar">
            {user.username.charAt(0).toUpperCase()}
          </div>

          <div>
            <strong>{user.username}</strong>
            <small>{connected ? "Live" : "Connecting..."}</small>
          </div>

          <button className="logout-btn" onClick={logout}>
            Log out
          </button>
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

          <span className="demo-tag">
            {connected ? "Live collaboration" : "Connecting..."}
          </span>
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
              <div className="avatar">
                {m.username?.charAt(0).toUpperCase() || "U"}
              </div>

              <div className="message-body">
                <div className="message-meta">
                  <strong>{m.username}</strong>
                  <time>
                    {new Date(m.created_at).toLocaleTimeString(
                      [],
                      {
                        hour: "2-digit",
                        minute: "2-digit",
                      }
                    )}
                  </time>
                </div>

                <p>{m.content}</p>
              </div>
            </div>
          ))}

          <div ref={messagesEndRef} />
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
              disabled={!selected || sending}
            />

            <button
              type="submit"
              disabled={!selected || !message.trim() || sending}
              aria-label="Send message"
            >
              <Send size={19} />
            </button>
          </form>

          <p className="hint">
            Messages are saved in PostgreSQL.
          </p>
        </div>
      </main>
    </div>
  );
}
