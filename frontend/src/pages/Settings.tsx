import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Skill } from "../types";
import { CONSULT_MODE_CHANNEL } from "../shared";

export default function Settings({ role }: { role: string }) {
  const [mode, setMode] = useState<"production" | "sandbox">("sandbox");
  const [rounds, setRounds] = useState(2);
  const [style, setStyle] = useState("brief");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selSkills, setSelSkills] = useState<number[]>([]);
  const [backendHealth, setBackendHealth] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState(false);
  const [useBuiltIn, setUseBuiltIn] = useState(true);
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmModel, setLlmModel] = useState("glm-4.5-air");
  const [llmApiKey, setLlmApiKey] = useState("");

  useEffect(() => {
    // 从本地存储恢复 LLM 配置（仅前端会话使用，安全起见不写回服务端）
    try {
      const cfg = JSON.parse(localStorage.getItem("mc_llm_cfg") || "null");
      if (cfg) {
        setUseBuiltIn(!cfg.external);
        if (cfg.endpoint) setLlmEndpoint(cfg.endpoint);
        if (cfg.model) setLlmModel(cfg.model);
        if (cfg.apiKey) setLlmApiKey(cfg.apiKey);
      }
    } catch { /* ignore */ }
    api.get<{ items: Skill[] }>("/api/skills").then((d) => {
      setSkills(d.items);
      setSelSkills(d.items.filter((s) => s.active).map((s) => s.id));
    }).catch(() => {});
    api.get<Record<string, unknown>>("/api/health").then((d) => setBackendHealth(d)).catch(() => {});
  }, []);

  function saveSettings() {
    setErr("");
    // LLM 配置持久化
    try {
      localStorage.setItem("mc_llm_cfg", JSON.stringify({
        external: !useBuiltIn,
        endpoint: llmEndpoint,
        model: llmModel,
        apiKey: llmApiKey,
      }));
    } catch { /* ignore */ }
    skills.forEach((s) => {
      const active = selSkills.includes(s.id);
      if (active !== s.active) {
        api.post(`/api/skills/${s.id}/update`, { active }).catch(() => {});
      }
    });

    try {
      new BroadcastChannel(CONSULT_MODE_CHANNEL).postMessage({ mode });
    } catch {}

    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div>
      <h1 className="page">系统设置</h1>
      <p className="sub">配置会诊运行模式、默认参数、LLM 连接和技能包</p>
      {err && <div className="flag-banner">{err}</div>}
      {saved && <div className="flag-banner" style={{ borderColor: "var(--success)", color: "var(--success)" }}>✅ 设置已保存</div>}

      {/* 运行模式 */}
      <div className="panel" style={{ marginTop: 20 }}>
        <div className="panel-title">运行模式</div>
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">默认模式</div>
            <div className="muted">选择系统默认运行的模式</div>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <button className={`btn ${mode === "production" ? "primary" : ""}`} onClick={() => setMode("production")}>
              🏥 生产模式
            </button>
            <button className={`btn ${mode === "sandbox" ? "primary" : ""}`} onClick={() => setMode("sandbox")}>
              🧪 沙箱模式
            </button>
          </div>
        </div>
        <div className="setting-desc">
          {mode === "production"
            ? "内置 Agnes 模型，报告可用于临床决策，支持打印和入病案"
            : "确定性演示模式，报告标注'演示'，禁止打印和入病案"}
        </div>
      </div>

      {/* 会诊参数 */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">会诊参数</div>

        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">讨论轮次</div>
            <div className="muted">控制专科医生交叉讨论的轮数（1-4 轮）</div>
          </div>
          <select value={rounds} onChange={(e) => setRounds(Number(e.target.value))} style={{ minWidth: 160 }}>
            <option value={1}>1 轮（独立意见）</option>
            <option value={2}>2 轮（交叉讨论）</option>
            <option value={3}>3 轮（深入讨论）</option>
            <option value={4}>4 轮（专家会诊）</option>
          </select>
        </div>

        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">报告风格</div>
            <div className="muted">生成报告的详略程度和风格</div>
          </div>
          <select value={style} onChange={(e) => setStyle(e.target.value)} style={{ minWidth: 160 }}>
            <option value="brief">简要风格（要点式）</option>
            <option value="detailed">详细风格（完整论述）</option>
            <option value="evidence">循证风格（含证据链）</option>
          </select>
        </div>
      </div>

      {/* LLM 配置 */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">LLM 模型配置</div>
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">使用外部 LLM</div>
            <div className="muted">生产模式必须配置外部 LLM 服务（如 OpenAI / GLM / 自建 API），此处配置仅保存至本地存储</div>
          </div>
          <label className="toggle">
            <input type="checkbox" checked={!useBuiltIn} onChange={(e) => setUseBuiltIn(!e.target.checked)} />
            <span className="slider"></span>
          </label>
        </div>

        {!useBuiltIn && (
          <>
            {(mode === "production" && !llmEndpoint) && (
              <div className="flag-banner" style={{ marginBottom: 16, borderColor: "var(--danger)", color: "var(--danger)" }}>
                ⚠️ 生产模式未配置 LLM 端点，将无法发起真实会诊。请填写下方 API 信息或切换到沙箱模式测试。
              </div>
            )}
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">API 端点</div>
                <div className="muted">LLM 服务的完整 URL（如 https://api.openai.com/v1）</div>
              </div>
              <input type="url" placeholder="https://api.openai.com/v1" value={llmEndpoint} onChange={(e) => setLlmEndpoint(e.target.value)} style={{ flex: 1, maxWidth: 400 }} />
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">模型名称</div>
                <div className="muted">如 gpt-4o、glm-4、deepseek-chat 等</div>
              </div>
              <input type="text" placeholder="gpt-4o" value={llmModel} onChange={(e) => setLlmModel(e.target.value)} style={{ minWidth: 160 }} />
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">API 密钥</div>
                <div className="muted">访问 LLM 服务的密钥（仅保存在浏览器本地，不上传服务器）</div>
              </div>
              <input type="password" placeholder="sk-..." value={llmApiKey} onChange={(e) => setLlmApiKey(e.target.value)} style={{ flex: 1, maxWidth: 300 }} />
            </div>
          </>
        )}
      </div>

      {/* 技能包管理 */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">技能包管理</div>
        <div className="muted" style={{ marginBottom: 12 }}>选择启用的会诊技能包，可影响会诊生成的深度和广度</div>
        <div className="skills-grid">
          {skills.map((s) => (
            <div key={s.id} className={`skill-card ${s.active ? "active" : ""}`} onClick={() => setSelSkills((p) => p.includes(s.id) ? p.filter((x) => x !== s.id) : [...p, s.id])}>
              <div className="skill-check">{s.active ? "✓" : ""}</div>
              <div className="skill-name">{s.name}</div>
              <div className="skill-desc">{s.desc}</div>
            </div>
          ))}
          {skills.length === 0 && <div className="muted" style={{ padding: 16 }}>暂无技能包，请联系管理员配置</div>}
        </div>
      </div>

      {/* 系统信息 */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">系统信息</div>
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">应用名称</div>
            <div className="muted">汇诊 · 多学科 AI 会诊平台</div>
          </div>
          <div className="muted">v0.9.0</div>
        </div>
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">当前角色</div>
            <div className="muted">仅管理员可修改系统和用户配置</div>
          </div>
          <span className={`badge ${role === "admin" ? "danger" : role === "chief" ? "warn" : "gray"}`}>
            {role === "admin" ? "管理员" : role === "chief" ? "主任" : "医生"}
          </span>
        </div>
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">后端服务</div>
            <div className="muted">FastAPI / SQLite</div>
          </div>
          {backendHealth ? (
            <span className="badge approved">运行中</span>
          ) : (
            <span className="badge rejected">未连接</span>
          )}
        </div>
      </div>

      <div className="row" style={{ marginTop: 24, paddingTop: 16, borderTop: "2px solid var(--border)" }}>
        <div style={{ flex: 1 }} />
        <button className="btn primary lg" onClick={saveSettings}>
          💾 保存设置
        </button>
      </div>
    </div>
  );
}
