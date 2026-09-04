import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";

interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
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

export default function Admin({ currentUserId }: { currentUserId: number }) {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [tab, setTab] = useState<"users" | "audit">("users");
  const [err, setErr] = useState("");

  const [form, setForm] = useState({ username: "", password: "", full_name: "", role: "doctor" });

  const [resetTarget, setResetTarget] = useState<number | null>(null);
  const [resetPwd, setResetPwd] = useState("");

  const [editTarget, setEditTarget] = useState<{ id: number; name: string; role: string } | null>(null);

  const [auditFilter, setAuditFilter] = useState({ action: "", resource: "", from: "", to: "" });

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
    if (!form.username.trim() || !form.password.trim()) {
      setErr("用户名和密码不能为空");
      return;
    }
    try {
      await api.post("/api/auth/register", form);
      setForm({ username: "", password: "", full_name: "", role: "doctor" });
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  async function resetPwdAction(uid: number) {
    setResetTarget(uid);
    setResetPwd("");
  }

  async function submitReset() {
    if (!resetTarget || resetPwd.length < 8) return;
    try {
      await api.post(`/api/users/${resetTarget}/reset-password?new_password=${encodeURIComponent(resetPwd)}`);
      setResetTarget(null);
      setResetPwd("");
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "重置失败");
    }
  }

  async function toggleActive(uid: number, active: boolean) {
    if (uid === currentUserId) {
      setErr("不能停用当前登录账号");
      return;
    }
    try {
      await api.post(`/api/users/${uid}/update`, { is_active: !active });
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "更新失败");
    }
  }

  async function saveEdit() {
    if (!editTarget) return;
    try {
      await api.post(`/api/users/${editTarget.id}/update`, {
        full_name: editTarget.name,
        role: editTarget.role,
      });
      setEditTarget(null);
      loadUsers();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "保存失败");
    }
  }

  const filteredAudit = audit.filter((a) => {
    if (auditFilter.action && !a.action.includes(auditFilter.action)) return false;
    if (auditFilter.resource && !a.resource_type.includes(auditFilter.resource)) return false;
    if (auditFilter.from && a.created_at && a.created_at < auditFilter.from) return false;
    if (auditFilter.to && a.created_at && a.created_at > auditFilter.to + "T23:59:59") return false;
    return true;
  });

  const roleLabel = (r: string) => r === "admin" ? "管理员" : r === "chief" ? "主任" : "医生";
  const actionLabel = (a: string) => {
    const map: Record<string, string> = {
      "auth.login": "登录",
      "user.create": "创建用户",
      "user.update": "更新用户",
      "consultation.create": "发起会诊",
      "consultation.followup": "跟进会诊",
      "feedback.submit": "提交反馈",
      "feedback.review": "审核反馈",
    };
    return map[a] || a;
  };

  return (
    <div>
      <h1 className="page">系统管理</h1>
      <p className="sub">用户与角色管理、审计日志（所有关键操作全程留痕）</p>
      <div className="toolbar">
        <button className={`btn sm ${tab === "users" ? "primary" : ""}`} onClick={() => setTab("users")}>用户管理</button>
        <button className={`btn sm ${tab === "audit" ? "primary" : ""}`} onClick={() => setTab("audit")}>审计日志</button>
      </div>
      {err && <div className="flag-banner">{err}</div>}
      {resetTarget != null && (
        <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 8, padding: 12, marginTop: 8 }}>
          <div className="muted" style={{ marginBottom: 6, fontSize: 13 }}>重置用户 #{resetTarget} 的密码</div>
          <div className="row" style={{ gap: 8 }}>
            <input type="password" placeholder="新密码（至少 8 位）" value={resetPwd} onChange={(e) => setResetPwd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitReset()} />
            <button className="btn primary sm" onClick={submitReset}>确认</button>
            <button className="btn sm" onClick={() => setResetTarget(null)}>取消</button>
          </div>
        </div>
      )}

      {tab === "users" && (
        <div className="panel">
          <div className="panel" style={{ background: "#f8fafc", margin: "0 0 16px 0", borderRadius: 8 }}>
            <div className="muted" style={{ marginBottom: 6, fontSize: 13 }}>新建账号</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input type="text" placeholder="用户名" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} style={{ minWidth: 120 }} />
              <input type="password" placeholder="初始密码" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} style={{ minWidth: 120 }} />
              <input type="text" placeholder="姓名" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} style={{ minWidth: 100 }} />
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="doctor">医生</option>
                <option value="chief">主任</option>
                <option value="admin">管理员</option>
              </select>
              <button className="btn primary sm" onClick={createUser}>创建</button>
            </div>
          </div>
          <table className="tbl">
            <thead><tr><th>ID</th><th>用户名</th><th>姓名</th><th>角色</th><th>创建时间</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td><strong>{u.username}</strong>{u.id === currentUserId && <span className="badge" style={{ marginLeft: 4, fontSize: 10 }}>我</span>}</td>
                  <td>
                    {editTarget?.id === u.id ? (
                      <input type="text" value={editTarget.name} onChange={(e) => setEditTarget({ ...editTarget, name: e.target.value })} style={{ width: 80, padding: "2px 6px" }} />
                    ) : (
                      u.full_name || <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    {editTarget?.id === u.id ? (
                      <select value={editTarget.role} onChange={(e) => setEditTarget({ ...editTarget, role: e.target.value })} style={{ padding: "2px 4px" }}>
                        <option value="admin">管理员</option>
                        <option value="chief">主任</option>
                        <option value="doctor">医生</option>
                      </select>
                    ) : (
                      <span className={`badge ${u.role === "admin" ? "danger" : u.role === "chief" ? "warn" : "gray"}`}>{roleLabel(u.role)}</span>
                    )}
                  </td>
                  <td className="muted">{u.created_at ? new Date(u.created_at).toLocaleDateString("zh-CN") : "—"}</td>
                  <td><span className={`badge ${u.is_active ? "approved" : "rejected"}`}>{u.is_active ? "启用" : "停用"}</span></td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      {editTarget?.id === u.id ? (
                        <>
                          <button className="btn primary sm" onClick={saveEdit}>保存</button>
                          <button className="btn sm" onClick={() => setEditTarget(null)}>取消</button>
                        </>
                      ) : (
                        <>
                          <button className="btn sm" onClick={() => setEditTarget({ id: u.id, name: u.full_name, role: u.role })}>编辑</button>
                          <button className="btn sm" onClick={() => resetPwdAction(u.id)}>重置密码</button>
                          {u.id !== currentUserId && (
                            <button className={`btn sm ${u.is_active ? "danger" : ""}`} onClick={() => toggleActive(u.id, u.is_active)}>
                              {u.is_active ? "停用" : "启用"}
                            </button>
                          )}
                        </>
                      )}
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
          <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <input type="text" placeholder="操作类型..." value={auditFilter.action} onChange={(e) => setAuditFilter({ ...auditFilter, action: e.target.value })} style={{ minWidth: 120 }} />
            <input type="text" placeholder="资源类型..." value={auditFilter.resource} onChange={(e) => setAuditFilter({ ...auditFilter, resource: e.target.value })} style={{ minWidth: 120 }} />
            <input type="date" value={auditFilter.from} onChange={(e) => setAuditFilter({ ...auditFilter, from: e.target.value })} style={{ minWidth: 140 }} />
            <input type="date" value={auditFilter.to} onChange={(e) => setAuditFilter({ ...auditFilter, to: e.target.value })} style={{ minWidth: 140 }} />
            <button className="btn sm" onClick={() => loadAudit()}>刷新</button>
          </div>
          <table className="tbl">
            <thead><tr><th>时间</th><th>操作</th><th>资源</th><th>详情</th><th>IP</th></tr></thead>
            <tbody>
              {filteredAudit.map((a) => (
                <tr key={a.id}>
                  <td className="muted">{a.created_at ? new Date(a.created_at).toLocaleString("zh-CN") : ""}</td>
                  <td>
                    <span className="badge gray">{actionLabel(a.action)}</span>
                  </td>
                  <td className="muted">{a.resource_type}{a.resource_id ? ` #${a.resource_id}` : ""}</td>
                  <td className="muted" style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.detail}</td>
                  <td className="muted">{a.ip}</td>
                </tr>
              ))}
              {filteredAudit.length === 0 && <tr><td colSpan={5} className="empty">暂无审计记录</td></tr>}
            </tbody>
          </table>
          {filteredAudit.length > 0 && (
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>显示 {filteredAudit.length} / {audit.length} 条记录</div>
          )}
        </div>
      )}
    </div>
  );
}
