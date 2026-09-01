import { useState } from "react";
import { api, ApiError, Me } from "../api";

export default function Login({ onLogin }: { onLogin: (token: string, user: Me) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const data = await api.post<{ access_token: string; user: Me }>("/api/auth/login", {
        username,
        password,
      });
      onLogin(data.access_token, data.user);
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>MedConsult Pro · 汇诊</h1>
        <p>医院多学科 AI 会诊平台 · 请使用院内账号登录</p>
        <label>用户名</label>
        <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        <label>密码</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <div className="err">{err}</div>
        <button className="btn primary" style={{ width: "100%", marginTop: 6 }} disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
    </div>
  );
}
