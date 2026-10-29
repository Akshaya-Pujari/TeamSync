
import { useEffect, useRef, useState } from "react";
import {
  Hash, Plus, Send, Users, Copy, LogOut
} from "lucide-react";
import { io } from "socket.io-client";
import Auth from "./Auth";
import "./App.css";

const API = "/api";

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }

  return data;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  const [workspaces, setWorkspaces] = useState([]);
  const [workspace, setWorkspace] = useState(null);
  const [channels, setChannels] = useState([]);
  const [selected, setSelected] = useState(null);

  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);

  const selectedRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    apiRequest("/auth/me")
      .then((data) => setUser(data.user))
      .catch(() => setUser(null))
      .finally(() => setCheckingAuth(false));
  }, []);

  // Load workspaces after login.
  useEffect(() => {
    if (!user) return;

    let active = true;

    apiRequest("/workspaces")
      .then((data) => {
        if (!active) return;

        setWorkspaces(data);

        const savedId = Number(
          localStorage.getItem(`teamsync_workspace_${user.id}`)
        );

        setWorkspace(
          data.find((w) => w.id === savedId) || data[0] || null
        );
      })
      .catch((err) => {
        if (active) setError(err.message);
      });

    return () => {
      active = false;
    };
  }, [user]);

  // Load workspace channels.
  useEffect(() => {
    if (!workspace || !user) {
      setChannels([]);
      setSelected(null);
      return;
    }

    let active = true;

    localStorage.setItem(
      `teamsync_workspace_${user.id}`,
      String(workspace.id)
    );

    setSelected(null);
    setMessages([]);

    apiRequest(`/workspaces/${workspace.id}/channels`)
      .then((data) => {
        if (!active) return;

        setChannels(data);

        const savedId = Number(
          localStorage.getItem(
            `teamsync_channel_${user.id}_${workspace.id}`
          )
        );

        setSelected(
          data.find((c) => c.id === savedId) || data[0] || null
        );
      })
      .catch((err) => {
        if (active) setError(err.message);
      });

    return () => {
      active = false;
    };
  }, [workspace, user]);

  useEffect(() => {
    selectedRef.current = selected;

    if (user && workspace && selected) {
      localStorage.setItem(
        `teamsync_channel_${user.id}_${workspace.id}`,
        String(selected.id)
      );
    }
  }, [selected, workspace, user]);

  // Load saved messages.
  useEffect(() => {
    if (!selected || !user) return;

    let active = true;
    const channelId = selected.id;

    setMessages([]);

    apiRequest(`/channels/${channelId}/messages`)
      .then((data) => {
        if (active) {
          setMessages((prev) => {
            const merged = new Map();
            data.forEach((m) => merged.set(m.id, m));
            prev.forEach((m) => merged.set(m.id, m));

            return [...merged.values()].sort(
              (a, b) => a.id - b.id
            );
          });
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      });

    return () => {
      active = false;
    };
  }, [selected, user]);

  // Real-time messages.
  useEffect(() => {
    if (!selected || !user) return;

    const channelId = selected.id;

    const socket = io("/", {
      path: "/socket.io",
      transports: ["polling", "websocket"],
      reconnection: true,
    });

    socket.on("connect", () => {
      setConnected(true);

      socket.emit("join_channel", {
        channel_id: channelId,
      });

      apiRequest(`/channels/${channelId}/messages`)
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
        .catch(console.error);
    });

    socket.on("new_message", (incoming) => {
      if (incoming.channel_id !== channelId) return;

      setMessages((prev) => {
        if (prev.some((m) => m.id === incoming.id)) return prev;

        return [...prev, incoming].sort(
          (a, b) => a.id - b.id
        );
      });
    });

    socket.on("disconnect", () => setConnected(false));
    socket.on("connect_error", () => setConnected(false));

    return () => {
      socket.disconnect();
      setConnected(false);
    };
  }, [selected, user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  async function createWorkspace() {
    const name = window.prompt("Workspace name:");
    if (!name?.trim()) return;

    try {
      const created = await apiRequest("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });

      const newWorkspace = {
        id: created.id,
        name: created.name,
        role: "owner",
      };

      setWorkspaces((prev) => [...prev, newWorkspace]);
      setWorkspace(newWorkspace);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function joinWorkspace() {
    const invite_code = window.prompt("Enter workspace invite code:");
    if (!invite_code?.trim()) return;

    try {
      const joined = await apiRequest("/workspaces/join", {
        method: "POST",
        body: JSON.stringify({
          invite_code: invite_code.trim(),
        }),
      });

      const existing = workspaces.find((w) => w.id === joined.id);

      if (!existing) {
        setWorkspaces((prev) => [
          ...prev,
          { ...joined, role: "member" },
        ]);
      }

      setWorkspace(existing || { ...joined, role: "member" });
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function copyInviteCode() {
    if (!workspace) return;

    try {
      const data = await apiRequest(
        `/workspaces/${workspace.id}/invite`
      );

      await navigator.clipboard.writeText(data.invite_code);
      window.alert("Invite code copied!");
    } catch (err) {
      setError(err.message);
    }
  }

  async function addChannel() {
    if (!workspace) return;

    const name = window.prompt("Channel name:");
    if (!name?.trim()) return;

    try {
      const created = await apiRequest(
        `/workspaces/${workspace.id}/channels`,
        {
          method: "POST",
          body: JSON.stringify({ name: name.trim() }),
        }
      );

      setChannels((prev) => [...prev, created]);
      setSelected(created);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendMessage(e) {
    e.preventDefault();

    if (!selected || !message.trim() || sending) return;

    const content = message.trim();
    const channelId = selected.id;

    setSending(true);

    try {
      const saved = await apiRequest(
        `/channels/${channelId}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        }
      );

      if (selectedRef.current?.id === channelId) {
        setMessages((prev) =>
          prev.some((m) => m.id === saved.id)
            ? prev
            : [...prev, saved]
        );
      }

      setMessage("");
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  async function logout() {
    try {
      await apiRequest("/auth/logout", {
        method: "POST",
      });

      setUser(null);
      setWorkspaces([]);
      setWorkspace(null);
      setChannels([]);
      setSelected(null);
      setMessages([]);
      setError("");
    } catch (err) {
      setError(err.message);
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

        <div className="workspace-controls">
          <label>YOUR WORKSPACE</label>

          <select
            className="workspace-select"
            value={workspace?.id || ""}
            onChange={(e) => {
              const next = workspaces.find(
                (w) => w.id === Number(e.target.value)
              );
              setWorkspace(next || null);
            }}
          >
            {workspaces.length === 0 && (
              <option value="">No workspaces yet</option>
            )}

            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>

          <div className="workspace-actions">
            <button onClick={createWorkspace}>
              <Plus size={14} /> Create
            </button>

            <button onClick={joinWorkspace}>
              <Users size={14} /> Join
            </button>
          </div>

          {workspace?.role === "owner" && (
            <button
              className="invite-btn"
              onClick={copyInviteCode}
            >
              <Copy size={14} /> Copy invite code
            </button>
          )}
        </div>

        <div className="channel-heading">
          <span>CHANNELS</span>
          <button
            onClick={addChannel}
            disabled={!workspace}
            title="Add channel"
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
            <small>
              {connected ? "Live" : "Offline"}
            </small>
          </div>

          <button
            className="logout-btn"
            onClick={logout}
            title="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h2>
              <Hash size={23} />
              {selected?.name || "Welcome to TeamSync"}
            </h2>
            <p>
              {workspace
                ? `${workspace.name} · Team conversations`
                : "Create or join a workspace to begin."}
            </p>
          </div>

          <span className="demo-tag">
            {connected ? "Live collaboration" : "TeamSync"}
          </span>
        </header>

        <section className="messages">
          {!workspace && (
            <div className="empty">
              <Users size={38} />
              <h3>Your workspace starts here.</h3>
              <p>Create a workspace or join one with an invite code.</p>
            </div>
          )}

          {workspace && messages.length === 0 && (
            <div className="empty">
              <Hash size={38} />
              <h3>Start the conversation.</h3>
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
                      { hour: "2-digit", minute: "2-digit" }
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
            >
              <Send size={19} />
            </button>
          </form>

          <p className="hint">
            Secure workspace conversations · PostgreSQL
          </p>
        </div>
      </main>
    </div>
  );
}
