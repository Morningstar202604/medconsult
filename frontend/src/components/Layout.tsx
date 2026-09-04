import { useState } from "react";
import { Me } from "../api";
import Dashboard from "../pages/Dashboard";
import Consultations from "../pages/Consultations";
import Patients from "../pages/Patients";
import Feedback from "../pages/Feedback";
import Knowledge from "../pages/Knowledge";
import Admin from "../pages/Admin";
import Settings from "../pages/Settings";

const NAV = [
  { key: "dashboard", label: "工作台", icon: "🏥", roles: ["admin", "chief", "doctor"] },
  { key: "consultations", label: "会诊记录", icon: "📋", roles: ["admin", "chief", "doctor"] },
  { key: "patients", label: "患者管理", icon: "👥", roles: ["admin", "chief", "doctor"] },
  { key: "knowledge", label: "知识库", icon: "📚", roles: ["admin", "chief", "doctor"] },
  { key: "feedback", label: "反馈审核", icon: "✅", roles: ["admin", "chief"] },
  { key: "settings", label: "系统设置", icon: "⚙️", roles: ["admin", "chief", "doctor"] },
  { key: "admin", label: "用户管理", icon: "🔐", roles: ["admin"] },
];

export default function Layout({
  user,
  page,
  onNavigate,
  onLogout,
}: {
  user: Me;
  page: string;
  onNavigate: (p: string) => void;
  onLogout: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const navs = NAV.filter((n) => n.roles.includes(user.role));
  const current = navs.find((n) => n.key === page) ? page : navs[0].key;

  return (
    <div className="app">
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <div className="brand">
            {!collapsed && <span>汇诊</span>}
            <small>{!collapsed && "多学科 AI 会诊平台"}</small>
          </div>
          <button className="collapse-btn" onClick={() => setCollapsed(!collapsed)} title={collapsed ? "展开导航" : "收起导航"}>
            {collapsed ? "→" : "←"}
          </button>
        </div>
        <nav>
          {navs.map((n) => (
            <a
              key={n.key}
              className={current === n.key ? "active" : ""}
              onClick={() => onNavigate(n.key)}
              title={collapsed ? n.label : undefined}
            >
              <span className="nav-icon">{n.icon}</span>
              {!collapsed && <span className="nav-label">{n.label}</span>}
            </a>
          ))}
        </nav>
        {!collapsed && (
          <div className="user">
            <b>{user.full_name || user.username}</b>
            <div style={{ color: "#94a3b8", fontSize: 11.5 }}>
              {user.role === "admin" ? "管理员" : user.role === "chief" ? "主任" : "医生"}
            </div>
            <div className="logout" onClick={onLogout}>
              退出登录
            </div>
          </div>
        )}
      </aside>
      <main className="main">
        {current === "dashboard" && <Dashboard user={user} />}
        {current === "consultations" && <Consultations user={user} />}
        {current === "patients" && <Patients />}
        {current === "feedback" && <Feedback user={user} />}
        {current === "knowledge" && <Knowledge />}
        {current === "settings" && <Settings role={user.role} />}
        {current === "admin" && <Admin currentUserId={user.id} />}
      </main>
    </div>
  );
}
