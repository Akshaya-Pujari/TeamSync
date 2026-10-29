
import { useState } from "react";

export default function Auth({ onLogin }) {
  const [register, setRegister] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: ""
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const endpoint = register ? "register" : "login";

      const res = await fetch(
       `/api/auth/${endpoint}`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form)
        }
      );

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Authentication failed");
      }

      onLogin(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">T</div>
        <span className="auth-eyebrow">WELCOME TO TEAMSYNC</span>
        <h1>{register ? "Join the conversation." : "Welcome back."}</h1>
        <p>One space for thoughtful teamwork.</p>

        <form onSubmit={submit}>
          {register && (
            <input
              placeholder="Username"
              required
              maxLength={80}
              value={form.username}
              onChange={e => setForm({
                ...form, username: e.target.value
              })}
            />
          )}

          <input
            type="email"
            placeholder="Email address"
            required
            value={form.email}
            onChange={e => setForm({
              ...form, email: e.target.value
            })}
          />

          <input
            type="password"
            placeholder="Password"
            required
            minLength={register ? 12 : undefined}
            value={form.password}
            onChange={e => setForm({
              ...form, password: e.target.value
            })}
          />

          {error && <p className="auth-error">{error}</p>}

          <button disabled={loading}>
            {loading ? "Please wait..." : register ? "Create account" : "Sign in"}
          </button>
        </form>

        <button
          className="auth-switch"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register
            ? "Already have an account? Sign in"
            : "New here? Create an account"}
        </button>
      </div>
    </div>
  );
}
