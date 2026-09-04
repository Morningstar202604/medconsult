import { useEffect, useState } from "react";
import { api, ApiError, Me } from "../api";
import type { ConsultationItem, Patient, FeedbackItem, ConsultMode } from "../types";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { AgentConsole } from "../components/AgentConsole";
import { AgentRulesPanel } from "../components/AgentRulesPanel";

export default function Dashboard({ user }: { user: Me }) {
  const [mode, setMode] = useLocalStorageState<ConsultMode>("consult_mode", "sandbox");
  const [stats, setStats] = useState({
    totalConsultations: 0,
    todayConsultations: 0,
    totalPatients: 0,
    pendingFeedback: 0,
  });
  const [recentConsultations, setRecentConsultations] = useState<ConsultationItem[]>([]);
  const [err, setErr] = useState("");

  const loadStats = () => {
    Promise.all([
      api.get<{ items: ConsultationItem[] }>("/api/consultations").catch(() => ({ items: [] })),
      api.get<{ items: Patient[] }>("/api/patients").catch(() => ({ items: [] })),
      api.get<{ items: FeedbackItem[] }>("/api/feedback").catch(() => ({ items: [] })),
    ]).then(([cons, patients, feedbacks]) => {
      const items = (cons as { items: ConsultationItem[] }).items;
      const today = new Date().toLocaleDateString("zh-CN");
      setStats({
        totalConsultations: items.length,
        todayConsultations: items.filter((c) => c.created_at && new Date(c.created_at).toLocaleDateString("zh-CN") === today).length,
        totalPatients: (patients as { items: Patient[] }).items.length,
        pendingFeedback: (feedbacks as { items: FeedbackItem[] }).items.filter((f) => f.status === "pending").length,
      });
      setRecentConsultations(items.slice(0, 5));
    }).catch(() => setErr("加载数据失败"));
  };

  useEffect(() => {
    loadStats();
  }, []);

  function openConsult(cid: number) {
    // 跳转到会诊页并按 ID 打开详情（consultations 页通过 ?open= 参数自动打开）
    window.location.hash = `#/consultations?open=${cid}`;
  }

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 24 }}>
        <div>
          <h1 className="page">会诊工作台</h1>
          <p className="sub">汇诊 · 多学科 AI 会诊平台 — {user.full_name || user.username}</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className={`badge ${mode === "production" ? "production" : "sandbox"}`}>{mode === "production" ? "生产模式" : "沙箱模式"}</span>
          {user.role === "admin" && <span className="badge approved">已认证</span>}
        </div>
      </div>

      {err && <div className="flag-banner">{err}</div>}

      {/* 统一智能入口（意图分流） */}
      <div className="panel" style={{ marginBottom: 24 }}>
        <AgentConsole user={user} onOpenConsult={openConsult} onRefreshList={loadStats} />
      </div>

      <AgentRulesPanel />{/* 统计卡片 */}
      <div className="stats-grid" style={{ marginBottom: 24 }}>
        <StatCard title="今日会诊" value={stats.todayConsultations} icon="📅" color="#3b82f6" />
        <StatCard title="总会诊数" value={stats.totalConsultations} icon="🏥" color="#10b981" />
        <StatCard title="管理患者" value={stats.totalPatients} icon="👥" color="#8b5cf6" />
        <StatCard title="待审核反馈" value={stats.pendingFeedback} icon="✅" color="#f59e0b" />
      </div>

      {/* 快速操作 */}
      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="panel-title">快速操作</div>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <QuickAction label="发起新会诊" icon="🚀" action="consultations" />
          <QuickAction label="患者管理" icon="👥" action="patients" />
          <QuickAction label="知识库" icon="📚" action="knowledge" />
          <QuickAction label="反馈审核" icon="✅" action="feedback" />
        </div>
      </div>

      {/* 最近会诊 */}
      <div className="panel">
        <div className="panel-title">最近会诊</div>
        <table className="tbl">
          <thead>
            <tr>
              <th>标题</th>
              <th>状态</th>
              <th>模式</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {recentConsultations.map((c) => (
              <tr key={c.id}>
                <td>{c.title || `会诊 #${c.id}`}</td>
                <td>
                  {c.status === "completed" ? <span className="badge approved">完成</span> :
                   c.status === "failed" ? <span className="badge danger">失败</span> :
                   <span className="badge warn">进行中</span>}
                </td>
                <td><span className={`badge ${c.mode === "production" ? "production" : "sandbox"}`}>{c.mode === "production" ? "生产" : "沙箱"}</span></td>
                <td className="muted">{c.created_at ? new Date(c.created_at).toLocaleString("zh-CN") : "—"}</td>
              </tr>
            ))}
            {recentConsultations.length === 0 && (
              <tr><td colSpan={4} className="empty">暂无会诊记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon, color }: { title: string; value: number; icon: string; color: string }) {
  return (
    <div className="stat-card" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="stat-icon" style={{ background: `${color}15`, color }}>{icon}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="muted" style={{ fontSize: 12 }}>{title}</div>
      </div>
    </div>
  );
}

function QuickAction({ label, icon, action }: { label: string; icon: string; action: string }) {
  return (
    <button className="btn" onClick={() => (window.location.hash = "#/" + action)} style={{ flex: "1 1 120px", justifyContent: "center" }}>
      <span style={{ fontSize: 20 }}>{icon}</span>
      <span>{label}</span>
    </button>
  );
}
