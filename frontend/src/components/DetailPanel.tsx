import { useState } from "react";
import { api, ApiError, getToken } from "../api";
import type { ConsultationDetail, EventItem } from "../types";
import { ReportCard } from "./ReportCard";

interface DetailPanelProps {
  detail: ConsultationDetail;
  onClose: () => void;
  followupText: string;
  setFollowupText: (v: string) => void;
  followBusy: boolean;
  followup: () => void;
}

export function DetailPanel({ detail, onClose, followupText, setFollowupText, followBusy, followup }: DetailPanelProps) {
  const [helpful, setHelpful] = useState<boolean | null>(null);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);
  const [fbBusy, setFbBusy] = useState(false);
  const [fbErr, setFbErr] = useState("");
  async function submitFeedback() {
    if (helpful == null) return;
    setFbBusy(true);
    setFbErr("");
    try {
      await api.post("/api/feedback", {
        consultation_id: detail.id,
        title: detail.title,
        diagnosis: detail.report?.final_diagnosis || "",
        helpful,
        note,
      });
      setSent(true);
    } catch (e) {
      setFbErr(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setFbBusy(false);
    }
  }
  const hasSpecialistRounds = detail.events.some((e) => e.round > 0);
  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 16 }}>
        <h1 className="page" style={{ fontSize: 16, margin: 0 }}>
          {detail.title}{" "}
          <span className={`badge ${detail.mode === "production" ? "production" : "sandbox"}`}>
            {detail.mode === "production" ? "生产" : "沙箱"}
          </span>{" "}
          {detail.is_demo && <span className="badge sandbox">演示</span>}
        </h1>
        <div className="row" style={{ gap: 8 }}>
          {detail.report && (
            <button
              className="btn sm"
              title="导出打印版报告（新窗口打开，可打印或另存 PDF）"
              onClick={() => {
                const url = `/api/consultations/${detail.id}/export`;
                const token = getToken();
                // 后端 export 需要 Authorization；带 token 同源导航（新窗口打开前先验证）
                fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
                  .then((r) => r.blob())
                  .then((blob) => {
                    const obj = URL.createObjectURL(blob);
                    const w = window.open(obj, "_blank");
                    if (w) w.addEventListener("load", () => URL.revokeObjectURL(obj));
                  })
                  .catch(() => {
                    window.open(`/api/consultations/${detail.id}/export`, "_blank");
                  });
              }}
            >
              🖨 导出 PDF
            </button>
          )}
          <button className="btn sm" onClick={onClose}>关闭</button>
        </div>
      </div>
      {detail.error_msg && <div className="flag-banner">{detail.error_msg}</div>}

      <div className="panel-title" style={{ marginBottom: 12, fontSize: 14, color: "#334155" }}>
        📋 会诊讨论过程
        {hasSpecialistRounds && (
          <span className="muted" style={{ fontWeight: 400, marginLeft: 8 }}>
            {detail.events.filter((e) => e.round > 0).length} 条发言 · 共 {Math.max(...detail.events.map((e) => e.round), 1)} 轮
          </span>
        )}
      </div>

      <div className="timeline">
        {detail.events.length === 0 && (
          <div className="muted" style={{ padding: "24px 0", textAlign: "center" }}>暂无讨论记录</div>
        )}
        {detail.events.map((e, i) => (
          <TimelineItem key={i} ev={e} />
        ))}
      </div>

      {detail.report && <ReportCard report={detail.report} evidence={detail.evidence} isDemo={detail.is_demo} />}
      {detail.tool_calls && detail.tool_calls.length > 0 && <ToolAuditPanel calls={detail.tool_calls} />}
      {detail.status === "completed" && detail.report && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>报告追问（向主持人就本报告提问，需生产模型）</div>
          <div className="row">
            <input className="flex" type="text" value={followupText}
              placeholder="例如：这个诊断还需要什么检查来确认？" onChange={(e) => setFollowupText(e.target.value)} />
            <button className="btn primary" disabled={followBusy || !followupText.trim()} onClick={followup}>
              {followBusy ? "思考中…" : "追问"}
            </button>
          </div>
        </div>
      )}
      {detail.status === "completed" && detail.report && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>反馈（经审核后可能纳入后续会诊经验）</div>
          {sent ? (
            <div className="muted">✅ 已提交，等待主任审核。</div>
          ) : (
            <>
              <div className="row">
                <button className={`btn sm ${helpful === true ? "primary" : ""}`} onClick={() => setHelpful(true)}>👍 报告有帮助</button>
                <button className={`btn sm ${helpful === false ? "primary" : ""}`} onClick={() => setHelpful(false)}>👎 有问题</button>
                <input className="flex" type="text" placeholder="补充说明（可选）" value={note} onChange={(e) => setNote(e.target.value)} />
                <button className="btn primary" disabled={fbBusy || helpful == null} onClick={submitFeedback}>
                  {fbBusy ? "提交中…" : "提交"}
                </button>
              </div>
              {fbErr && <div className="muted" style={{ color: "var(--danger)", marginTop: 6 }}>{fbErr}</div>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TimelineItem({ ev }: { ev: EventItem }) {
  if (ev.role === "triage") {
    return <div className="flag-banner">🚨 <b>危急征象识别</b>：{ev.text}</div>;
  }
  if (ev.role === "dispute") {
    return (
      <div className="tl-item">
        <div className="tl-av" style={{ background: "#fff1f0", color: "#cf1322" }}>⚔️</div>
        <div className="tl-body">
          <div className="h"><b>专科分歧（已显性化）</b></div>
          <p>{ev.text}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="tl-item">
      <div className={`tl-av ${ev.role === "triage" ? "triage" : ""}`}>{ev.emoji || "•"}</div>
      <div className="tl-body">
        <div className="h">
          <b>{ev.name}</b>
          {ev.round > 0 && <span className="round"> · 第 {ev.round} 轮{ev.round === 1 ? "意见" : "讨论"}</span>}
        </div>
        <p>{ev.text}</p>
      </div>
    </div>
  );
}

function ToolAuditPanel({ calls }: { calls: import("../types").ToolCall[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 12 }}>
      <button className="btn sm" onClick={() => setOpen(!open)}>
        🛠️ 临床工具调用审计（{calls.length} 次）{open ? "收起" : "展开"}
      </button>
      {open && (
        <div className="panel" style={{ marginTop: 8, padding: 10 }}>
          {calls.map((t) => (
            <div key={t.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 2px" }}>
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <span className="badge production">{t.tool_name}</span>
                <span className="muted">置信度 {t.confidence}</span>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>输入：{JSON.stringify(t.input)}</div>
              <div style={{ fontSize: 12.5, marginTop: 2 }}>输出：{typeof t.output === "object" ? (t.output as { summary?: string }).summary || JSON.stringify(t.output) : JSON.stringify(t.output)}</div>
              {t.note && <div className="muted" style={{ fontSize: 12 }}>备注：{t.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
