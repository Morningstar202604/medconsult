import { useEffect, useState } from "react";
import { api } from "../api";

interface RulesData {
  safety_baseline: string;
  red_flags: { total: number; by_severity: Record<string, { count: number; examples: string[] }> };
  drug_interactions: { total: number; by_severity: Record<string, number> };
  evidence_levels: Record<string, string>;
  intents: { intent: string; label: string }[];
  calculators: { name: string; desc: string }[];
  roles: string[];
}

const SEV_LABEL: Record<string, string> = { emergent: "立即急诊", urgent: "尽快就医", review: "需要关注" };
const DRUG_LABEL: Record<string, string> = { major: "高危", moderate: "中危", minor: "低危" };

export function AgentRulesPanel() {
  const [rules, setRules] = useState<RulesData | null>(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get<RulesData>("/api/agent/rules").then(setRules).catch((e) => setErr(e instanceof Error ? e.message : "加载失败"));
  }, []);

  if (err || !rules) {
    if (err) return <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>内置规则加载失败：{err}</div>;
    return <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>加载内置规则…</div>;
  }

  return (
    <details className="agent-rules" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="agent-rules-summary">🛡️ 系统内置规则与安全基线（共 {rules.red_flags.total} 条危急红旗 · {rules.drug_interactions.total} 条药物互作）</summary>
      <div className="agent-rules-body">
        <div className="rule-sec">
          <div className="rule-sec-title">AI 安全基线（每条会诊都强制注入的提示词）</div>
          <div className="rule-sec-text">{rules.safety_baseline}</div>
        </div>

        <div className="rule-sec">
          <div className="rule-sec-title">🚨 危急红旗扫描（确定性规则，不依赖模型判断）</div>
          <div className="rule-grid">
            {Object.entries(rules.red_flags.by_severity).map(([sev, info]) => (
              <div key={sev} className={`rule-card sev-${sev}`}>
                <b>{SEV_LABEL[sev] || sev} × {info.count}</b>
                <ul>{info.examples.map((ex, i) => <li key={i}>{ex}</li>)}</ul>
              </div>
            ))}
          </div>
        </div>

        <div className="rule-sec">
          <div className="rule-sec-title">💊 药物相互作用库（命中即给严重度与处理建议）</div>
          <div className="rule-row">
            {Object.entries(rules.drug_interactions.by_severity).map(([sev, n]) => (
              <span key={sev} className={`badge drug-${sev}`}>{DRUG_LABEL[sev] || sev}：{n} 条</span>
            ))}
          </div>
        </div>

        <div className="rule-sec">
          <div className="rule-sec-title">📚 证据分级（每条检索结果强制标注）</div>
          <div className="rule-row">
            {Object.entries(rules.evidence_levels).map(([k, v]) => (
              <span key={k} className="badge ev-ok">{k} 级{Array.from({ length: 4 - k.length }, () => "·").join("")}{v}</span>
            ))}
          </div>
        </div>

        <div className="rule-sec">
          <div className="rule-sec-title">🧭 意图路由（一条输入自动分流）</div>
          <div className="rule-row">
            {rules.intents.map((i) => (
              <span key={i.intent} className="badge">{i.label}</span>
            ))}
          </div>
          <div className="rule-sec-text muted">内置计算器：{rules.calculators.map((c) => c.name).join("、")}</div>
        </div>
      </div>
    </details>
  );
}