import { useState } from "react";
import type { Report, EvidenceItem } from "../types";

const BASIS_LABEL: Record<string, string> = {
  rule: "规则", calculator: "计算器", rag: "资料检索", specialist: "专科意见",
  moderator: "主持人", feedback: "本院经验", exam: "检查建议", drug: "药物互作",
};

interface ReportCardProps {
  report: Report;
  evidence: EvidenceItem[];
  isDemo: boolean;
}

export function ReportCard({ report, evidence, isDemo }: ReportCardProps) {
  const [view, setView] = useState<"professional" | "patient">("professional");
  const [showEvidence, setShowEvidence] = useState(false);
  if (!report) return null;
  const pr = report.patient_report;
  return (
    <div className="report-wrap" style={{ marginTop: 16 }}>
      {isDemo && <div className="demo-stamp">沙箱演示</div>}
      <div className="report-card">
        <div className="report-head">
          <h3>⚖️ 会诊共识报告</h3>
          {isDemo && <span className="badge sandbox">禁止打印 / 入病案</span>}
        </div>
        {pr && !isDemo && (
          <div className="row" style={{ marginBottom: 10 }}>
            <button className={`btn sm ${view === "professional" ? "primary" : ""}`} onClick={() => setView("professional")}>👨‍⚕️ 专业版</button>
            <button className={`btn sm ${view === "patient" ? "primary" : ""}`} onClick={() => setView("patient")}>👤 患者版</button>
            <span className="muted">{view === "patient" ? "面向患者的通俗解读" : "供临床参考的专业报告"}</span>
          </div>
        )}
        {view === "patient" && pr ? (
          <>
            <div className="report-grid">
              <div><div className="k">简单说</div><div className="v">{pr.summary}</div></div>
            </div>
            <div className="report-sec"><h4>可能是什么</h4><div>{pr.what_it_may_be}</div></div>
            <div className="report-sec"><h4>您需要做什么</h4><ul>{pr.what_to_do.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div className="report-sec"><h4>什么情况要马上去医院</h4><ul>{pr.when_to_seek_care.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div className="report-sec"><h4>就诊时可以问医生</h4><ul>{pr.questions_to_ask.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          </>
        ) : (
          <>
            <div className="report-grid">
              <div><div className="k">倾向判断（供参考）</div><div className="v">{report.final_diagnosis || "—"}</div></div>
              <div><div className="k">置信度</div><div className="v">{report.confidence || "—"}{report.data_completeness ? `（资料完备度 ${report.data_completeness}）` : ""}</div></div>
              <div><div className="k">建议就诊科室</div><div className="v">{report.recommended_dept || "—"}</div></div>
            </div>
            {report.missing_info && <div className="report-sec" style={{ borderTop: "1px solid var(--border)", background: "#fff7ed" }}>📋 {report.missing_info}</div>}
            {report.exam_suggestions && <div className="report-sec"><h4>🩻 建议检查（含优先级/不适用情形）</h4><div>{report.exam_suggestions}</div></div>}
            {report.drug_interactions && <div className="report-sec"><h4>💊 药物相互作用核查</h4><div>{report.drug_interactions}</div></div>}
            {report.key_findings?.length > 0 && (
              <div className="report-sec"><h4>主要依据</h4><ul>{report.key_findings.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            )}
            {report.plan?.length > 0 && (
              <div className="report-sec"><h4>方案建议</h4><ul>{report.plan.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            )}
            {report.calculations && report.calculations.length > 0 && (
              <div className="report-sec"><h4>🧮 工具计算（文本自动提取，未核实）</h4><ul>{report.calculations.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            )}
            {report.red_flags?.length > 0 && (
              <div className="report-danger">🚨 <b>紧急警示</b>：{report.red_flags.join("；")}</div>
            )}
            {report.disagreements && <div className="report-sec"><h4>分歧说明</h4><div>{report.disagreements}</div></div>}
            {report.dispute_detail && report.dispute_detail.length > 0 && (
              <div className="report-sec">
                <h4>专科分歧明细（显性化）</h4>
                <ul>
                  {report.dispute_detail.map((d, i) => (
                    <li key={i}><b>{d.topic}</b>：{d.summary}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="report-warn">⚠ {report.warnings || "本报告仅供临床参考，不构成处方。"}</div>
          </>
        )}
      </div>
      {!isDemo && (
        <div style={{ marginTop: 8 }}>
          <button className="btn sm" onClick={() => setShowEvidence(!showEvidence)}>
            🔗 证据链 {evidence.length > 0 ? `（${evidence.length} 条）` : ""} {showEvidence ? "收起" : "展开"}
          </button>
          {showEvidence && (
            <div className="panel" style={{ marginTop: 8, padding: 10 }}>
              {evidence.length === 0 && <div className="muted">暂无证据记录</div>}
              {evidence.map((e) => (
                <div key={e.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 2px" }}>
                  <div className="row" style={{ alignItems: "center", gap: 8 }}>
                    <span className="badge production">{BASIS_LABEL[e.basis_type] || e.basis_type}</span>
                    <span className="muted">置信度 {e.confidence}</span>
                  </div>
                  <div style={{ fontSize: 13, marginTop: 4 }}>{e.claim}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>来源：{e.source || "—"}</div>
                  {e.limitation && <div className="muted" style={{ fontSize: 12 }}>限制：{e.limitation}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
