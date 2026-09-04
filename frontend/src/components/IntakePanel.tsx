import { useState } from "react";
import { api, ApiError } from "../api";
import type { IntakeAnswerResp } from "../types";

interface IntakePanelProps {
  onComplete: (recordText: string) => void;
}

export function IntakePanel({ onComplete }: IntakePanelProps) {
  const [id, setId] = useState<number | null>(null);
  const [chief, setChief] = useState("");
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientGender, setPatientGender] = useState("");
  const [question, setQuestion] = useState<{ question: string; reason: string } | null>(null);
  const [answer, setAnswer] = useState("");
  const [progress, setProgress] = useState<{ answered: number; total: number }>({ answered: 0, total: 0 });
  const [busy, setBusy] = useState(false);
  const [interrupt, setInterrupt] = useState<{ message: string; severity: string } | null>(null);
  const [err, setErr] = useState("");
  const [started, setStarted] = useState(false);
  const [done, setDone] = useState(false);
  const [category, setCategory] = useState("");

  async function start() {
    if (!chief.trim()) { setErr("请先输入患者主诉，例如：胸痛2小时"); return; }
    if (!patientName.trim()) { setErr("请输入患者姓名"); return; }
    setErr("");
    setBusy(true);
    try {
      const d = await api.post<{ id: number; category_label: string; next_question: { question: string; reason: string }; progress: { answered: number; total: number } }>("/api/intake", {
        chief_complaint: chief.trim(),
        patient_name: patientName.trim(),
        patient_age: patientAge || undefined,
        patient_gender: patientGender || undefined,
      });
      setId(d.id);
      setCategory(d.category_label);
      setQuestion(d.next_question);
      setProgress(d.progress);
      setStarted(true);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "启动问诊失败");
    } finally {
      setBusy(false);
    }
  }
  async function submitAnswer() {
    if (!id || !answer.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const d = await api.post<IntakeAnswerResp>(`/api/intake/${id}/answer`, { answer: answer.trim() });
      setProgress(d.progress);
      if (d.interrupt && d.red_flags.length > 0) {
        const top = d.red_flags[0];
        setInterrupt({ message: top.message, severity: top.severity });
        setQuestion(null);
        return;
      }
      setAnswer("");
      if (d.done) {
        const c = await api.post<{ record: Record<string, string> }>(`/api/intake/${id}/complete`, { create_encounter: false });
        const record = c.record;
        const text = [
          `主诉：${record.chief_complaint || ""}`,
          `现病史：${record.history || ""}`,
          `既往史：${record.past_history || ""}`,
          `用药：${record.meds || ""}`,
          `辅助检查：${record.exams || ""}`,
          `生命体征：${record.vitals || ""}`,
        ].filter(Boolean).join("\n");
        onComplete(text);
        setDone(true);
        setQuestion(null);
      } else {
        setQuestion(d.next_question);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "提交回答失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 12, padding: "20px 24px", marginBottom: 12, background: "#f8fafc" }}>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 4, height: 18, background: "var(--accent)", borderRadius: 2 }}></span>
        🗣️ 采集式问诊
      </div>
      <div className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
        AI 会按主诉类别定向追问，每个问题都说明"为什么要问"（对应鉴别诊断）；出现危急征象将立即拦截。
      </div>
      {!started ? (
        <div>
          <div style={{ marginBottom: 12 }}>
            <div className="muted" style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>患者基本信息</div>
            <div className="row" style={{ gap: 12 }}>
              <input className="flex" type="text" placeholder="患者姓名 *" value={patientName} onChange={(e) => setPatientName(e.target.value)} style={{ flex: "0 0 120px" }} />
              <input type="number" placeholder="年龄" value={patientAge} onChange={(e) => setPatientAge(e.target.value)} style={{ minWidth: 80 }} />
              <select value={patientGender} onChange={(e) => setPatientGender(e.target.value)} style={{ minWidth: 80 }}>
                <option value="">性别</option>
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div className="muted" style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>主诉（必填）</div>
            <input className="flex" type="text" placeholder="例如：胸痛2小时伴出冷汗、头痛3天加重…" value={chief} onChange={(e) => setChief(e.target.value)} />
          </div>
          {err && <div className="muted" style={{ color: "var(--danger)", marginBottom: 8, fontSize: 13 }}>{err}</div>}
          <button className="btn primary" disabled={busy} onClick={start} style={{ padding: "10px 24px" }}>
            {busy ? "⏳ 启动中…" : "▶️ 开始问诊"}
          </button>
        </div>
      ) : interrupt ? (
        <div className="flag-banner" style={{ borderColor: "var(--danger)", padding: "16px 20px" }}>
          ⚠️ <b>{interrupt.severity === "emergent" ? "立即急诊" : "尽快就医"}</b>：{interrupt.message}
          <div className="muted" style={{ marginTop: 4 }}>已停止常规采集。请直接线下急诊，携带已录入信息。</div>
        </div>
      ) : done ? (
        <div style={{ padding: "16px 20px", background: "var(--ok-weak)", border: "1px solid var(--ok)", borderRadius: 8, color: "var(--ok)" }}>
          ✅ 问诊完成！结构化病历已填入下方"病情描述"，您可继续编辑后发起会诊。
        </div>
      ) : (
        <>
          <div className="muted" style={{ marginBottom: 12, padding: "8px 12px", background: "#fff", borderRadius: 6, border: "1px solid var(--border)" }}>
            类别：<b style={{ color: "var(--accent)" }}>{category}</b> · 进度 {progress.answered}/{progress.total}
            <div style={{ marginTop: 8, height: 4, background: "#e2e8f0", borderRadius: 2 }}>
              <div style={{ height: 4, background: "var(--accent)", borderRadius: 2, width: `${(progress.answered / Math.max(progress.total, 1)) * 100}%`, transition: "width 0.3s" }} />
            </div>
          </div>
          {question && (
            <div style={{ marginBottom: 16, padding: "16px 20px", background: "#fff", border: "1px solid var(--border)", borderRadius: 8 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8, color: "var(--text)" }}>❓ {question.question}</div>
              <div className="muted" style={{ fontSize: 12.5, padding: "8px 12px", background: "#f8fafc", borderRadius: 6 }}>
                💡 为什么问：{question.reason}
              </div>
            </div>
          )}
          <div className="row" style={{ gap: 12 }}>
            <input className="flex" type="text" placeholder="请输入回答…" value={answer} onChange={(e) => setAnswer(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") submitAnswer(); }} />
            <button className="btn primary" disabled={busy || !answer.trim()} onClick={submitAnswer} style={{ padding: "10px 24px" }}>
              {busy ? "⏳…" : "✓ 回答"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
