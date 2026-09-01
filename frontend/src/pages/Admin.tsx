import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";

interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
}
interface AuditRow {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: string;
  ip: string;
  created_at: string | null;
}

export default function Admin() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [tab, setTab] = useState<"users" | "audit">("users");
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ username: "", password: "", full_name: "", role: "doctor" });

  const loadUsers = useCallback(async () => {
    try {
      const d = await api.get<{ items: UserRow[] }>("/api/users");
      setUsers(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, []);

  const loadAudit = useCallback(async () => {
    try {
      const d = await api.get<{ items: AuditRow[] }>("/api/audit");
      setAudit(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    loadUsers();
    loadAudit();
  }, [loadUsers, loadAudit]);

  async function createUser() {
    try {
      await api.post("/api/auth/register", form);
      setForm({ username: "", password: "", full_name: "", role: "doctor" });
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  async function resetPwd(uid: number) {
    const pw = prompt("输入新密码（至少 8 位）");
    if (!pw) return;
    try {
      await api.post(`/api/users/${uid}/reset-password?new_password=${encodeURIComponent(pw)}`);
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "重置失败");
    }
  }

  async function toggleActive(uid: number, active: boolean) {
    try {
      await api.post(`/api/users/${uid}/update`, { is_active: !active });
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "更新失败");
    }
  }

  return (
    <div>
      <h1 className="page">系统管理</h1>
      <p className="sub">用户与角色管理、审计日志（所有关键操作全程留痕）</p>
      <div className="toolbar">
        <button className={`btn sm ${tab === "users" ? "primary" : ""}`} onClick={() => setTab("users")}>用户</button>
        <button className={`btn sm ${tab === "audit" ? "primary" : ""}`} onClick={() => setTab("audit")}>审计日志</button>
      </div>
      {err && <div className="flag-banner">{err}</div>}

      {tab === "users" && (
        <div className="panel">
          <div className="panel" style={{ background: "#f8fafc" }}>
            <div className="muted" style={{ marginBottom: 6 }}>新建账号</div>
            <div className="row">
              <input type="text" placeholder="用户名" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              <input type="password" placeholder="初始密码" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <input type="text" placeholder="姓名" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="doctor">医生</option>
                <option value="chief">主任</option>
                <option value="admin">管理员</option>
              </select>
              <button className="btn primary" onClick={createUser}>创建</button>
            </div>
          </div>
          <table className="tbl">
            <thead><tr><th>ID</th><th>用户名</th><th>姓名</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td><td>{u.username}</td><td>{u.full_name}</td>
                  <td>
                    <span className={`badge ${u.role === "admin" ? "danger" : u.role === "chief" ? "warn" : "gray"}`}>
                      {u.role === "admin" ? "管理员" : u.role === "chief" ? "主任" : "医生"}
                    </span>
                  </td>
                  <td><span className={`badge ${u.is_active ? "approved" : "rejected"}`}>{u.is_active ? "启用" : "停用"}</span></td>
                  <td>
                    <div className="row">
                      <button className="btn sm" onClick={() => resetPwd(u.id)}>重置密码</button>
                      <button className="btn sm danger" onClick={() => toggleActive(u.id, u.is_active)}>
                        {u.is_active ? "停用" : "启用"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "audit" && (
        <div className="panel">
          <table className="tbl">
            <thead><tr><th>时间</th><th>操作</th><th>资源</th><th>详情</th><th>IP</th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td className="muted">{a.created_at ? new Date(a.created_at).toLocaleString("zh-CN") : ""}</td>
                  <td>{a.action}</td>
                  <td className="muted">{a.resource_type}{a.resource_id ? `#${a.resource_id}` : ""}</td>
                  <td className="muted">{a.detail}</td>
                  <td className="muted">{a.ip}</td>
                </tr>
              ))}
              {audit.length === 0 && <tr><td colSpan={5} className="empty">暂无审计记录</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
