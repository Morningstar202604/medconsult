import { Me } from "../api";
import Consultations from "../pages/Consultations";
import Patients from "../pages/Patients";
import Feedback from "../pages/Feedback";
import Knowledge from "../pages/Knowledge";
import Admin from "../pages/Admin";

const NAV = [
  { key: "dashboard", label: "会诊工作台", roles: ["admin", "chief", "doctor"] },
  { key: "patients", label: "患者管理", roles: ["admin", "chief", "doctor"] },
  { key: "feedback", label: "反馈审核", roles: ["admin", "chief"] },
  { key: "knowledge", label: "知识库", roles: ["admin", "chief", "doctor"] },
  { key: "admin", label: "系统管理", roles: ["admin"] },
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
  const navs = NAV.filter((n) => n.roles.includes(user.role));
  const current = navs.find((n) => n.key === page) ? page : navs[0].key;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          MedConsult Pro
          <small>汇诊 · 多学科会诊平台</small>
        </div>
        <nav>
          {navs.map((n) => (
            <a key={n.key} className={current === n.key ? "active" : ""} onClick={() => onNavigate(n.key)}>
              {n.label}
            </a>
          ))}
        </nav>
        <div className="spacer" />
        <div className="user">
          <b>{user.full_name || user.username}</b>
          <div style={{ color: "#94a3b8", fontSize: 11.5 }}>
            {user.role === "admin" ? "系统管理员" : user.role === "chief" ? "主任" : "医生"}
          </div>
          <div className="logout" onClick={onLogout}>
            退出登录
          </div>
        </div>
      </aside>
      <main className="main">
        {current === "dashboard" && <Consultations user={user} />}
        {current === "patients" && <Patients />}
        {current === "feedback" && <Feedback user={user} />}
        {current === "knowledge" && <Knowledge />}
        {current === "admin" && <Admin />}
      </main>
    </div>
  );
}
