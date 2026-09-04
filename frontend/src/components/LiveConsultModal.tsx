import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { ConsultationDetail } from "../types";

interface LiveConsultModalProps {
  consultationId: number;
  title: string;
  onClose: () => void;
  onViewDetails: () => void;
}

export function LiveConsultModal({ consultationId, title, onClose, onViewDetails }: LiveConsultModalProps) {
  const [detail, setDetail] = useState<ConsultationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [inputText, setInputText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [userMessages, setUserMessages] = useState<{ text: string; timestamp: Date }[]>([]);
  const chatRef = useRef<HTMLDivElement>(null);
  const prevEventCount = useRef(0);

  useEffect(() => {
    const poll = async () => {
      try {
        const d = await api.get<ConsultationDetail>(`/api/consultations/${consultationId}`);
        setDetail(d);
        setLoading(false);

        const newEvents = d.events.slice(prevEventCount.current);
        if (newEvents.length > 0) {
          prevEventCount.current = d.events.length;
          // Auto-scroll to bottom when new events arrive
          setTimeout(() => {
            if (chatRef.current) {
              chatRef.current.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
            }
          }, 50);
        }

        if (d.status === "completed" || d.status === "failed") {
          setLoading(false);
        }
      } catch {
        if (loading) {
          // Still trying to load...
        }
      }
    };

    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [consultationId, loading]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTo({ top: chatRef.current.scrollHeight });
    }
  }, [detail?.events.length, userMessages.length]);

  async function sendInterjection() {
    if (!inputText.trim() || sending) return;
    const text = inputText.trim();
    setInputText("");
    setUserMessages((prev) => [...prev, { text, timestamp: new Date() }]);
    setSending(true);
    try {
      const d = await api.post<{ reply: string }>(`/api/consultations/${consultationId}/followup`, {
        consultation_id: consultationId,
        text,
      });
      setDetail((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          events: [
            ...prev.events,
            { role: "specialist", name: "你（追问）", emoji: "👤", round: 0, text: d.reply },
          ],
        };
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "追问失败");
      setUserMessages((prev) => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  }

  const isLive = detail?.status === "pending" || detail?.status === "running";
  const isDone = detail?.status === "completed";
  const isError = detail?.status === "failed";

  function getStageEmoji(role: string): string {
    switch (role) {
      case "triage": return "🚨";
      case "summary": return "📋";
      case "tool_call": return "🔧";
      case "specialist": return "👨‍⚕️";
      case "moderator": return "⚖️";
      case "dispute": return "⚔️";
      case "report": return "📄";
      default: return "🤖";
    }
  }

  function getStageName(role: string): string {
    switch (role) {
      case "triage": return "危急分诊";
      case "summary": return "病史摘要";
      case "tool_call": return "工具调用";
      case "specialist": return "专科意见";
      case "moderator": return "主持人";
      case "dispute": return "分歧讨论";
      case "report": return "共识报告";
      default: return role;
    }
  }

  function renderEvent(ev: { role: string; name: string; emoji: string; round: number; text: string }, index: number) {
    const isTriage = ev.role === "triage";
    const isUser = ev.name.includes("你（追问）") || ev.name === "你";

    if (isUser) {
      return (
        <div key={index} className="live-user-msg">
          <div className="lc-avatar">👤</div>
          <div>
            <div className="lc-name">你</div>
            <div className="lc-bubble">{ev.text}</div>
          </div>
        </div>
      );
    }

    if (isTriage) {
      return (
        <div key={index} className="live-triage-banner">
          <div className="lb-title">🚨 {getStageName(ev.role)}</div>
          <div className="lb-body">{ev.text}</div>
        </div>
      );
    }

    return (
      <div key={index} className={`live-agent-msg ${ev.round > 0 ? "agent-right" : "agent-left"}`}>
        <div className="lc-avatar">{ev.emoji || getStageEmoji(ev.role)}</div>
        <div>
          <div className="lc-name">
            {ev.name}
            {ev.round > 0 && <span className="lc-round-tag">第 {ev.round} 轮</span>}
          </div>
          <div className="lc-bubble">{ev.text}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="live-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="live-modal">
        {/* Header */}
        <div className="live-modal-header">
          <div className="live-badge">
            <div className="live-dot"></div>
            {isLive ? "会诊进行中" : isDone ? "会诊已完成" : isError ? "会诊失败" : "准备中"}
          </div>
          <h2>{title}</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        {/* Chat Area */}
        <div className="live-chat-area" ref={chatRef}>
          {loading && detail === null && (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <div className="live-typing" style={{ justifyContent: "center", marginBottom: 12 }}>
                <span></span><span></span><span></span>
              </div>
              <div className="muted" style={{ fontSize: 14 }}>正在初始化会诊...</div>
            </div>
          )}

          {detail && detail.events.length === 0 && !loading && (
            <div className="muted" style={{ textAlign: "center", padding: "40px 0" }}>
              等待智能体开始讨论...
            </div>
          )}

          {detail && detail.events.map((ev, i) => renderEvent(ev, i))}

          {userMessages.map((msg, i) => (
            <div key={`user-${i}`} className="live-user-msg">
              <div className="lc-avatar">👤</div>
              <div>
                <div className="lc-name">你</div>
                <div className="lc-bubble">{msg.text}</div>
              </div>
            </div>
          ))}

          {isLive && (
            <div className="live-system-note">
              <span>
                <div className="live-typing" style={{ display: "inline-flex", verticalAlign: "middle", marginRight: 8 }}>
                  <span></span><span></span><span></span>
                </div>
                智能体正在讨论中...
              </span>
            </div>
          )}

          {isError && detail.error_msg && (
            <div className="live-triage-banner danger">
              <div className="lb-title">❌ 会诊失败</div>
              <div className="lb-body">{detail.error_msg}</div>
            </div>
          )}
        </div>

        {/* Input Area */}
        {(isLive || isDone) && (
          <div className="live-input-area">
            <div className="input-hint">
              💡 讨论过程中可随时插入追问或补充信息
            </div>
            <div className="live-input-row">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendInterjection(); } }}
                placeholder={isLive ? "输入追问或补充信息..." : "会诊已完成，可查看详情"}
                disabled={!isLive && !isDone}
              />
              <button
                className="send-btn"
                onClick={sendInterjection}
                disabled={sending || (!inputText.trim()) || (!isLive && !isDone)}
              >
                {sending ? "⏳" : "发送"}
              </button>
            </div>
            {error && <div className="muted" style={{ color: "var(--danger)", marginTop: 8, fontSize: 13 }}>{error}</div>}
          </div>
        )}

        {/* Done Banner */}
        {isDone && detail && (
          <div style={{ padding: "0 24px 16px", flexShrink: 0 }}>
            <div className="live-done-banner">
              <div className="done-icon">✅</div>
              <div className="done-text">
                <h4>会诊已完成</h4>
                <p>
                  {detail.report?.final_diagnosis && `倾向诊断：${detail.report.final_diagnosis}`}
                  {!detail.report?.final_diagnosis && "报告已生成"}
                </p>
              </div>
              <div className="done-actions">
                <button onClick={onViewDetails}>查看详情</button>
                <button className="view-btn" onClick={() => { onViewDetails(); onClose(); }}>打开报告</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
