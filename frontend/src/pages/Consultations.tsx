import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Me, uploadMedia } from "../api";
import { MediaUploadPanel } from "../components/MediaUploadPanel";
import type {
  ConsultationDetail, ConsultationItem, Doc, Encounter, EventItem, EvidenceItem, IntakeAnswerResp,
  Patient, Report, Skill, ToolCall, MediaAsset,
} from "../types";
const SPECS: Record<string, string> = {
  internal: "内科", surgery: "外科", pharmacy: "药学", labimaging: "影像检验",
  neurology: "神经内科", cardio: "心内科", pediatrics: "儿科", obgyn: "妇产科",
};
export default function Consultations({ user }: { user: Me }) {
  const [list, setList] = useState<ConsultationItem[]>([]);
  const [modeFilter, setModeFilter] = useState("");
  const [detail, setDetail] = useState<ConsultationDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("production");
  const [specs, setSpecs] = useState<string[]>(["internal", "surgery", "pharmacy", "labimaging"]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [selPatient, setSelPatient] = useState<number | "">("");
  const [selEncounter, setSelEncounter] = useState<number | "">("");
  const [selSkills, setSelSkills] = useState<number[]>([]);
  const [selDocs, setSelDocs] = useState<number[]>([]);
  const [style, setStyle] = useState("brief");
  const [rounds, setRounds] = useState(2);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [followupText, setFollowupText] = useState("");
  const [followBusy, setFollowBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const data = await api.get<{ items: ConsultationItem[] }>(
        "/api/consultations" + (modeFilter ? `?mode=${modeFilter}` : "")
      );
      setList(data.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, [modeFilter]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    api.get<{ items: Skill[] }>("/api/skills").then((d) => setSkills(d.items)).catch(() => {});
    api.get<{ items: Doc[] }>("/api/library").then((d) => setDocs(d.items)).catch(() => {});
    api.get<{ items: Patient[] }>("/api/patients").then((d) => setPatients(d.items)).catch(() => {});
  }, []);
  async function loadEncounters(pid: number | "") {
    if (pid === "") {
      setEncounters([]);
      setSelEncounter("");
      return;
    }
    try {
      const d = await api.get<{ items: Encounter[] }>(`/api/patients/${pid}/encounters`);
      setEncounters(d.items);
    } catch {
      setEncounters([]);
    }
  }
  async function create() {
    setErr("");
    if (!text.trim() && selEncounter === "") {
      setErr("请填写病情描述，或选择已有就诊记录");
      return;
    }
    setBusy(true);
    try {
      const d = await api.post<ConsultationDetail>("/api/consultations", {
        mode, text: text.trim(), encounter_id: selEncounter === "" ? null : selEncounter,
        specialties: specs, skills: selSkills, doc_ids: selDocs, style, rounds,
      });
      setShowCreate(false);
      setText("");
      setDetail(d);
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "发起失败");
    } finally {
      setBusy(false);
    }
  }
  async function openDetail(id: number) {
    try {
      const d = await api.get<ConsultationDetail>(`/api/consultations/${id}`);
      setDetail(d);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "读取失败");
    }
  }
  async function followup() {
    if (!detail || !followupText.trim()) return;
    setFollowBusy(true);
    try {
      const d = await api.post<{ reply: string }>(`/api/consultations/${detail.id}/followup`, {
        consultation_id: detail.id, text: followupText.trim(),
      });
      setDetail({
        ...detail,
        events: [...detail.events, { role: "specialist", name: "会诊主持人（追问）", emoji: "⚖️", round: 0, text: d.reply }],
      });
      setFollowupText("");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "追问失败");
    } finally {
      setFollowBusy(false);
    }
  }
  function toggleSpec(s: string) {
    setSpecs((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }
  return (
    <div>
      <div className="row spread">
        <div>
          <h1 className="page">会诊工作台</h1>
          <p className="sub">采集式问诊 → 多学科 AI 会诊：危急分诊 → 专科意见 → 共识报告 → 证据链 → 追问</p>
        </div>
        <button className="btn primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "收起" : "＋ 发起会诊"}
        </button>
      </div>
      {err && <div className="flag-banner">{err}</div>}
      {showCreate && (
        <div className="panel">
          <IntakePanel onComplete={(recordText) => { setText(recordText); }} />
          <MediaUploadPanel onText={(t) => setText((prev) => (prev ? prev + "\n" + t : t))} />
          <div className="row" style={{ margin: "12px 0 10px" }}>
            <span className="muted">运行模式</span>
            <button className={`btn sm ${mode === "production" ? "primary" : ""}`} onClick={() => setMode("production")}>
              生产模式
            </button>
            <button className={`btn sm ${mode === "sandbox" ? "primary" : ""}`} onClick={() => setMode("sandbox")}>
              沙箱演示
            </button>
            <span className="muted">
              {mode === "production" ? "真实模型会诊（需配置 LLM）" : "确定性演示，报告禁止打印/入病案"}
            </span>
          </div>
          <div style={{ marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 4 }}>关联患者/就诊（可选）</div>
            <div className="row">
              <select value={selPatient} onChange={(e) => { setSelPatient(e.target.value === "" ? "" : Number(e.target.value)); loadEncounters(e.target.value === "" ? "" : Number(e.target.value)); }}>
                <option value="">不关联患者</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}（{p.hospital_no || "无号"}）</option>
                ))}
              </select>
              <select value={selEncounter} onChange={(e) => setSelEncounter(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">不关联就诊</option>
                {encounters.map((en) => (
                  <option key={en.id} value={en.id}>
                    {en.visit_no || `就诊#${en.id}`}：{(en.chief_complaint || "").slice(0, 30)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 4 }}>病情描述 / 会诊内容（可用上方问诊自动填充）</div>
            <textarea
              rows={4} style={{ width: "100%" }} value={text}
              placeholder="描述患者症状、病程、既往史、已有检查结果等（生产模式下必填）"
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <div style={{ marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 4 }}>会诊专科</div>
            <div className="row">
              {Object.entries(SPECS).map(([k, v]) => (
                <button key={k} className={`btn sm ${specs.includes(k) ? "primary" : ""}`} onClick={() => toggleSpec(k)}>
                  {v}
                </button>
              ))}
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 4 }}>技能包</div>
            <div className="row">
              {skills.map((s) => (
                <button key={s.id} className={`btn sm ${selSkills.includes(s.id) ? "primary" : ""}`}
                  onClick={() => setSelSkills((p) => (p.includes(s.id) ? p.filter((x) => x !== s.id) : [...p, s.id]))}
                  title={s.prompt}>
                  {s.name}
                </button>
              ))}
              {skills.length === 0 && <span className="muted">无</span>}
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <div className="muted" style={{ marginBottom: 4 }}>引用文档（可选）</div>
            <div className="row">
              {docs.map((d) => (
                <button key={d.id} className={`btn sm ${selDocs.includes(d.id) ? "primary" : ""}`}
                  onClick={() => setSelDocs((p) => (p.includes(d.id) ? p.filter((x) => x !== d.id) : [...p, d.id]))}>
                  {d.name}
                </button>
              ))}
              {docs.length === 0 && <span className="muted">暂无文档（可在知识库上传）</span>}
            </div>
          </div>
          <div className="row">
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="brief">简要风格</option>
              <option value="detailed">详细风格</option>
              <option value="evidence">循证风格</option>
            </select>
            <select value={rounds} onChange={(e) => setRounds(Number(e.target.value))}>
              <option value={1}>1 轮（独立意见）</option>
              <option value={2}>2 轮（交叉讨论）</option>
            </select>
            <button className="btn primary" disabled={busy} onClick={create}>
              {busy ? "会诊进行中…" : "发起会诊"}
            </button>
          </div>
        </div>
      )}
      <div className="panel" style={{ padding: 10 }}>
        <div className="row" style={{ padding: "2px 8px 10px" }}>
          <button className={`btn sm ${modeFilter === "" ? "primary" : ""}`} onClick={() => setModeFilter("")}>全部</button>
          <button className={`btn sm ${modeFilter === "production" ? "primary" : ""}`} onClick={() => setModeFilter("production")}>生产</button>
          <button className={`btn sm ${modeFilter === "sandbox" ? "primary" : ""}`} onClick={() => setModeFilter("sandbox")}>沙箱</button>
        </div>
        <table className="tbl">
          <thead>
            <tr><th>标题</th><th>模式</th><th>状态</th><th>完备度</th><th>时间</th></tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.id} style={{ cursor: "pointer" }} onClick={() => openDetail(c.id)}>
                <td>{c.title}</td>
                <td><span className={`badge ${c.mode === "production" ? "production" : "sandbox"}`}>{c.mode === "production" ? "生产" : "沙箱"}</span></td>
                <td>
                  {c.status === "completed" ? <span className="badge approved">完成</span> :
                    c.status === "failed" ? <span className="badge danger">失败</span> :
                    <span className="badge warn">进行中</span>}
                </td>
                <td className="muted">{c.data_completeness}</td>
                <td className="muted">{c.created_at ? new Date(c.created_at).toLocaleString("zh-CN") : ""}</td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr><td colSpan={5} className="empty">暂无会诊记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {detail && <DetailPanel detail={detail} onClose={() => setDetail(null)} />}
      {detail && detail.status === "completed" && detail.mode === "production" && (
        <div className="panel">
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
    </div>
  );
}
// ---------------------------------------------------------------- 采集式问诊
function IntakePanel({ onComplete }: { onComplete: (recordText: string) => void }) {
  const [id, setId] = useState<number | null>(null);
  const [chief, setChief] = useState("");
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
    setErr("");
    setBusy(true);
    try {
      const d = await api.post<{ id: number; category_label: string; next_question: { question: string; reason: string }; progress: { answered: number; total: number } }>("/api/intake", { chief_complaint: chief.trim() });
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
        // 问诊完成 → 生成病历并回填
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
    <div style={{ border: "1px solid var(--border)", borderRadius: 12, padding: "10px 12px", marginBottom: 12, background: "#f8fafc" }}>
      <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 4 }}>🗣️ 采集式问诊（像医生问诊，不是聊天）</div>
      <div className="muted" style={{ marginBottom: 8 }}>
        AI 会按主诉类别定向追问，每个问题都说明"为什么要问"（对应鉴别诊断）；出现危急征象将立即拦截。完成问诊后自动生成结构化病历填入下方。
      </div>
      {!started ? (
        <div className="row">
          <input className="flex" type="text" placeholder="患者主诉，例如：胸痛2小时伴出冷汗" value={chief} onChange={(e) => setChief(e.target.value)} />
          <button className="btn primary" disabled={busy} onClick={start}>{busy ? "启动中…" : "开始问诊"}</button>
        </div>
      ) : interrupt ? (
        <div className="flag-banner" style={{ borderColor: "var(--danger)" }}>
          ⚠️ <b>{interrupt.severity === "emergent" ? "立即急诊" : "尽快就医"}</b>：{interrupt.message}
          <div className="muted" style={{ marginTop: 4 }}>已停止常规采集。请直接线下急诊，携带已录入信息。</div>
        </div>
      ) : done ? (
        <div className="muted" style={{ color: "var(--success)" }}>✅ 问诊完成，结构化病历已填入下方"病情描述"，可继续编辑后发起会诊。</div>
      ) : (
        <>
          <div className="muted" style={{ marginBottom: 6 }}>
            类别：<b>{category}</b> · 进度 {progress.answered}/{progress.total}
          </div>
          {question && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600 }}>❓ {question.question}</div>
              <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>💡 为什么问：{question.reason}</div>
            </div>
          )}
          <div className="row">
            <input className="flex" type="text" placeholder="回答（如：压榨样闷痛，活动后加重）" value={answer} onChange={(e) => setAnswer(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") submitAnswer(); }} />
            <button className="btn primary" disabled={busy || !answer.trim()} onClick={submitAnswer}>{busy ? "…" : "回答"}</button>
          </div>
        </>
      )}
      {err && <div className="muted" style={{ color: "var(--danger)", marginTop: 6 }}>{err}</div>}
    </div>
  );
}
// ---------------------------------------------------------------- 详情
function DetailPanel({ detail, onClose }: { detail: ConsultationDetail; onClose: () => void }) {
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
  return (
    <div className="panel">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h1 className="page" style={{ fontSize: 16 }}>
          {detail.title}{" "}
          <span className={`badge ${detail.mode === "production" ? "production" : "sandbox"}`}>
            {detail.mode === "production" ? "生产" : "沙箱"}
          </span>{" "}
          {detail.is_demo && <span className="badge sandbox">演示</span>}
        </h1>
        <button className="btn sm" onClick={onClose}>关闭</button>
      </div>
      {detail.error_msg && <div className="flag-banner">{detail.error_msg}</div>}
      <div className="timeline">
        {detail.events.map((e, i) => (
          <TimelineItem key={i} ev={e} />
        ))}
      </div>
      {detail.report && <ReportCard report={detail.report} evidence={detail.evidence} isDemo={detail.is_demo} />}
      {detail.tool_calls && detail.tool_calls.length > 0 && <ToolAuditPanel calls={detail.tool_calls} />}
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
// ---------------------------------------------------------------- 报告卡片（专业/患者双视角 + 证据链）
const BASIS_LABEL: Record<string, string> = {
  rule: "规则", calculator: "计算器", rag: "资料检索", specialist: "专科意见",
  moderator: "主持人", feedback: "本院经验", exam: "检查建议", drug: "药物互作",
};
function ReportCard({ report, evidence, isDemo }: { report: Report; evidence: EvidenceItem[]; isDemo: boolean }) {
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
// ---------------------------------------------------------------- 工具审计
function ToolAuditPanel({ calls }: { calls: ToolCall[] }) {
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
