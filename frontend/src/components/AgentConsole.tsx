import { useRef, useState } from "react";
import { api, copyText, streamSSE } from "../api";
import type { Me } from "../api";
import type { AgentResponse, AgentIntent } from "../types";

interface AgentConsoleProps {
  user: Me;
  onOpenConsult: (cid: number, title: string) => void;
  onRefreshList: () => void;
}

const INTENT_CHOICES: { v: AgentIntent; label: string }[] = [
  { v: "consult", label: "改用会诊" },
  { v: "intake", label: "改用问诊" },
  { v: "calculator", label: "医学计算" },
  { v: "drug", label: "用药安全" },
  { v: "knowledge", label: "知识问答" },
  { v: "literature", label: "循证检索" },
];

export function AgentConsole({ user, onOpenConsult, onRefreshList }: AgentConsoleProps) {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"sandbox" | "production">("sandbox");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<AgentResponse | null>(null);
  const [focused, setFocused] = useState(false);
  // SSE 流式
  const [streamEvents, setStreamEvents] = useState<{ name: string; emoji: string; text: string }[]>([]);
  const [reportText, setReportText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const streamCid = useRef<number | null>(null);

  async function send(forceIntent?: AgentIntent) {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setErr("");
    setStreamEvents([]);
    setReportText("");
    streamCid.current = null;
    try {
      const body: Record<string, unknown> = { text, mode };
      if (forceIntent) body.force_intent = forceIntent;
      const r = await api.post<AgentResponse>("/api/agent", body);
      setResult(r);
      if (r.action === "consult" && r.data && typeof r.data.id === "number") {
        streamCid.current = r.data.id as number;
      }
      onRefreshList();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "调用失败");
    } finally {
      setBusy(false);
    }
  }

  async function watchStream() {
    const cid = streamCid.current;
    if (cid == null || streaming) return;
    setStreaming(true);
    setStreamEvents([]);
    setReportText("");
    try {
      await streamSSE(`/api/consultations/${cid}/stream`, {
        onEvent: (ev, data) => {
          const d = data as { name?: string; emoji?: string; text?: string; chunk?: string };
          if (ev === "event" && d.name) {
            setStreamEvents((prev) => [...prev, { name: d.name!, emoji: d.emoji!, text: d.text! }]);
          } else if (ev === "report_chunk") {
            setReportText((prev) => prev + (d.chunk || ""));
          }
        },
        onDone: () => setStreaming(false),
      });
    } catch {
      setStreaming(false);
    }
  }

  function renderResult() {
    if (!result) return null;
    const action = result.action;
    const d = result.data;

    if (action === "consult") {
      const title = ((d.title as string) || "").slice(0, 40);
      return (
        <div className="agent-card">
          <div className="agent-intent-row">
            <span className="badge production">✅ 已分流：多学科会诊</span>
            <span className="muted">附：{result.intent.reason}</span>
          </div>
          {d.status === "completed" && (
            <div className="agent-actions">
              <button className="btn sm primary"
                onClick={() => onOpenConsult(streamCid.current!, title)}>
                查看完整会诊
              </button>
              <button className="btn sm" onClick={watchStream} disabled={streaming}>
                {streaming ? "⏳ 回放中..." : "▶️ 过程流式回放"}
              </button>
              {streamCid.current != null && (
                <button className="btn sm"
                  onClick={() => { void copyText(`${title}（会诊 #${streamCid.current}）`); }}>
                  📋 复制会话摘要
                </button>
              )}
            </div>
          )}
          <div className="agent-intent-row" style={{ marginTop: 8 }}>
            <span className="muted">识别不准？</span>
            {INTENT_CHOICES.map((c) => (
              <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>
            ))}
          </div>
        </div>
      );
    }

    if (action === "calculator") {
      const items = (d.items || []) as { name: string; expr: string; result: string; note: string }[];
      return (
        <div className="agent-card">
          <div className="agent-intent-row"><span className="badge production">🧮 医学计算</span><span className="muted">{result.intent.reason}</span></div>
          {items.length === 0 && <div className="muted">未识别到可用计算器</div>}
          {items.map((it, i) => (
            <div key={i} className="calc-row"><b>{it.name}</b>：{it.expr} = <b>{it.result}</b><div className="muted" style={{ fontSize: 12 }}>{it.note || ""}</div></div>
          ))}
          <div className="agent-intent-row" style={{ marginTop: 8 }}>
            <span className="muted">识别不准？</span>
            {INTENT_CHOICES.map((c) => <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>)}
          </div>
        </div>
      );
    }

    if (action === "drug") {
      return (
        <div className="agent-card">
          <div className="agent-intent-row"><span className="badge production">💊 用药安全</span><span className="muted">{result.intent.reason}</span></div>
          {d.summary && <div className="report-warn" style={{ marginBottom: 8 }}>{d.summary}</div>}
          {((d.items as unknown as Record<string, string>[]) || []).map((it, i) => (
            <div key={i} className="calc-row">{it.name || JSON.stringify(it)}</div>
          ))}
          <div className="agent-intent-row" style={{ marginTop: 8 }}>
            <span className="muted">识别不准？</span>
            {INTENT_CHOICES.map((c) => <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>)}
          </div>
        </div>
      );
    }

    if (action === "literature") {
      const results = (d.results || []) as { title: string; source: string; date: string; url: string; snippet: string; level: string }[];
      const labels = (d.level_labels || {}) as Record<string, string>;
      return (
        <div className="agent-card">
          <div className="agent-intent-row">
            <span className="badge production">📚 循证检索</span>
            <span className="muted">来源 {d.provider}，共 {d.count} 条{d.degraded ? "（内部资料库兜底）" : "（实时外部源）"}</span>
          </div>
          {results.length === 0 && <div className="muted">未检索到结果</div>}
          {results.map((r, i) => (
            <div key={i} className="lit-row">
              <div className="row" style={{ alignItems: "center", gap: 8 }}>
                <span className={`badge level-${r.level}`}>{r.level} 级</span>
                <span className="muted" style={{ fontSize: 12 }}>{labels[r.level] || ""}</span>
              </div>
              <div style={{ fontWeight: 600, margin: "4px 0" }}>
                {r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.title}</a> : r.title}
              </div>
              <div className="muted" style={{ fontSize: 12 }}>{r.source} · {r.date || "—"}</div>
              <div style={{ fontSize: 13, color: "var(--text2, #555)" }}>{r.snippet}</div>
            </div>
          ))}
          <div className="agent-intent-row" style={{ marginTop: 8 }}>
            <span className="muted">识别不准？</span>
            {INTENT_CHOICES.map((c) => <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>)}
          </div>
        </div>
      );
    }

    if (action === "knowledge") {
      const refs = (d.references || []) as { item: string; en: string; unit: string; range: string; note: string }[];
      return (
        <div className="agent-card">
          <div className="agent-intent-row"><span className="badge production">📖 知识问答</span><span className="muted">{result.intent.reason}</span></div>
          {refs.length === 0 && <div className="muted">知识库中未找到匹配条目</div>}
          {refs.map((r, i) => (
            <div key={i} className="calc-row"><b>{r.item}</b>{r.en ? `（${r.en}）` : ""}：{r.range || r.note || "—"}{r.unit ? ` ${r.unit}` : ""}</div>
          ))}
          <div className="agent-intent-row" style={{ marginTop: 8 }}>
            <span className="muted">识别不准？</span>
            {INTENT_CHOICES.map((c) => <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>)}
          </div>
        </div>
      );
    }

    if (action === "redirect") {
      return (
        <div className="agent-card">
          <div className="agent-intent-row"><span className="badge production">🩺 采集式问诊</span><span className="muted">{result.intent.reason}</span></div>
          <div className="agent-actions" style={{ marginTop: 8 }}>
            <button className="btn sm primary" onClick={() => { window.location.hash = "#/consultations"; }}>
              开始结构化问诊 →
            </button>
            {INTENT_CHOICES.map((c) => <button key={c.v} className="btn xs" disabled={busy} onClick={() => send(c.v)}>{c.label}</button>)}
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="agent-console">
      <div className="agent-header">
        <div className="agent-title">🧠 智能会诊助手</div>
        <div className="muted" style={{ fontSize: 12 }}>
          输入任何内容：病情描述（自动进入 MDT）、计算器（如"BMI 计算"）、用药疑问、文献检索、指南问答——系统自动分流
        </div>
      </div>
      <div className="agent-input-row">
        <input
          className="agent-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => setFocused(true)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
          placeholder='例：58岁男性胸痛伴冷汗3小时… / 计算 GRACE 评分 / 华法林和阿司匹林能一起吃吗 / 检索房颤抗凝最新文献'
          disabled={busy}
        />
        <select className="mode-select" value={mode} onChange={(e) => setMode(e.target.value as "sandbox" | "production")} disabled={busy}>
          <option value="sandbox">沙箱</option>
          <option value="production">生产</option>
        </select>
        <button className="send-btn" onClick={() => void send()} disabled={busy || !input.trim()}>
          {busy ? "⏳" : "发送"}
        </button>
      </div>
      {err && <div className="muted" style={{ color: "var(--danger,#d33)", fontSize: 13, marginTop: 6 }}>{err}</div>}

      {focused && (streaming || streamEvents.length > 0 || reportText) && (
        <div className="agent-stream">
          <div className="agent-stream-title">📡 会诊过程直播{focused ? "（回放）" : ""}</div>
          {streamEvents.map((ev, i) => (
            <div key={i} className="stream-row">
              <span>{ev.emoji || "🤖"}</span>
              <span className="stream-name">{ev.name}:</span>
              <span className="stream-text">{ev.text.length > 90 ? ev.text.slice(0, 90) + "…" : ev.text}</span>
            </div>
          ))}
          {reportText && (
            <details open>
              <summary className="stream-report-trigger">📄 共识报告（打字机）</summary>
              <pre className="stream-report">{reportText}</pre>
            </details>
          )}
        </div>
      )}

      {renderResult()}
    </div>
  );
}