import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, Me, uploadMedia } from "../api";
import { MediaUploadPanel } from "../components/MediaUploadPanel";
import { LiveConsultModal } from "../components/LiveConsultModal";
import { IntakePanel } from "../components/IntakePanel";
import { DetailPanel } from "../components/DetailPanel";
import { SPECIALTIES, CONSULT_MODE_CHANNEL, DEFAULT_SPECIALTIES } from "../shared";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import type {
  ConsultationDetail, ConsultationItem, Doc, Encounter, EventItem, EvidenceItem, IntakeAnswerResp,
  Patient, Report, Skill, ToolCall, MediaAsset, ConsultMode, SpecialtyKey,
} from "../types";
export default function Consultations({ user }: { user: Me }) {
  const [list, setList] = useState<ConsultationItem[]>([]);
  const [modeFilter, setModeFilter] = useState("");
  const [detail, setDetail] = useState<ConsultationDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showLiveModal, setShowLiveModal] = useState(false);
  const [liveConsultId, setLiveConsultId] = useState<number | null>(null);
  const [liveConsultTitle, setLiveConsultTitle] = useState("");
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"production" | "sandbox">(() => {
    try { return (localStorage.getItem("consult_mode") as "production" | "sandbox") || "production"; } catch { return "production"; }
  });
  const [specs, setSpecs] = useState<import("../types").SpecialtyKey[]>(() => {
    try {
      const saved = localStorage.getItem("consult_specs");
      if (saved) return JSON.parse(saved) as import("../types").SpecialtyKey[];
    } catch { /* ignore */ }
    return DEFAULT_SPECIALTIES as import("../types").SpecialtyKey[];
  });
  const [skills, setSkills] = useState<Skill[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [selPatient, setSelPatient] = useState<number | "">("");
  const [selEncounter, setSelEncounter] = useState<number | "">("");
  const [selSkills, setSelSkills] = useState<number[]>([]);
  const [selDocs, setSelDocs] = useState<number[]>([]);
  const [style, setStyle] = useLocalStorageState<"brief" | "detailed" | "evidence">("consult_style", "brief");
  const [rounds, setRounds] = useLocalStorageState<number>("consult_rounds", 2, {
    read: (raw) => Number(raw) || 2,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [followupText, setFollowupText] = useState("");
  const [followBusy, setFollowBusy] = useState(false);
  const channelRef = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    try {
      const bc = new BroadcastChannel(CONSULT_MODE_CHANNEL);
      channelRef.current = bc;
      bc.onmessage = (e: MessageEvent) => {
        if (e.data && typeof e.data.mode === "string") {
          setMode(e.data.mode as ConsultMode);
        }
      };
    } catch {}
    return () => { channelRef.current?.close(); };
  }, []);
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
  // 支持 ?open=<id> 自动打开详情（来自工作台 AgentConsole 跳转）
  useEffect(() => {
    const m = window.location.hash.match(/[?&]open=(\d+)/);
    if (m) {
      const id = Number(m[1]);
      if (Number.isFinite(id) && id > 0) {
        void openDetail(id);
        const clean = window.location.hash.replace(/[?&]open=\d+/, "");
        window.location.hash = clean || "#/consultations";
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
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
      setLiveConsultId(d.id);
      setLiveConsultTitle(d.title);
      setShowLiveModal(true);
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
  function toggleSpec(s: SpecialtyKey) {
    setSpecs((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }
  async function removeConsult(id: number, title: string) {
    if (!window.confirm(`确认删除会诊「${title || `#${id}`}」？删除后不可恢复。`)) return;
    try {
      await api.del(`/api/consultations/${id}`);
      if (detail?.id === id) setDetail(null);
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "删除失败");
    }
  }
  return (
    <div>
      <div className="row spread" style={{ marginBottom: 24 }}>
        <div>
          <h1 className="page">会诊工作台</h1>
          <p className="sub">采集式问诊 → 多学科 AI 会诊：危急分诊 → 专科意见 → 共识报告 → 证据链 → 追问</p>
        </div>
        <button className="btn primary lg" onClick={() => setShowCreate(!showCreate)}>
          <span>{showCreate ? "收起" : "＋ 发起会诊"}</span>
        </button>
      </div>
      {err && <div className="flag-banner">{err}</div>}
      {showCreate && (
        <div className="panel">
          <IntakePanel onComplete={(recordText) => { setText(recordText); }} />
          <MediaUploadPanel onText={(t) => setText((prev) => (prev ? prev + "\n" + t : t))} />

          <div className="flag-banner" style={{ marginBottom: 16, borderColor: "var(--warn)", color: "var(--warn)" }}>
            ⚠️ <b>发起会诊前请确认 LLM 配置：</b>若您使用「生产模式」，请先前往 <a href="#/settings" style={{ color: "inherit", textDecoration: "underline" }}>系统设置 → LLM 模型配置</a> 填写 API 端点与密钥；未配置时生产模式将拒绝发起请求。当前可使用「沙箱模式」进行演示测试。
          </div>

          <div style={{ marginTop: 24, marginBottom: 20, borderBottom: "2px solid #e2e8f0", paddingBottom: 20 }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 14, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 4, height: 16, background: "var(--accent)", borderRadius: 2 }}></span>
              运行模式（从「系统设置」加载）
            </div>
            <div className="row" style={{ gap: 16 }}>
              <button className={`btn ${mode === "production" ? "primary" : ""}`} onClick={() => setMode("production")}>
                🏥 生产模式
              </button>
              <button className={`btn ${mode === "sandbox" ? "primary" : ""}`} onClick={() => setMode("sandbox")}>
                🧪 沙箱演示
              </button>
              <span className="muted" style={{ marginLeft: 8, alignSelf: "center" }}>
                {mode === "production" ? "需先在「系统设置」配置 LLM" : "确定性演示，报告禁止打印/入病案"}
              </span>
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <div className="muted" style={{ marginBottom: 10, fontWeight: 500, fontSize: 13 }}>
              关联患者/就诊（可选）
            </div>
            <div className="row" style={{ gap: 16 }}>
              <select value={selPatient} onChange={(e) => { setSelPatient(e.target.value === "" ? "" : Number(e.target.value)); loadEncounters(e.target.value === "" ? "" : Number(e.target.value)); }} style={{ minWidth: 220, flex: "0 0 auto" }}>
                <option value="">不关联患者</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}（{p.hospital_no || "无号"}）</option>
                ))}
              </select>
              <select value={selEncounter} onChange={(e) => setSelEncounter(e.target.value === "" ? "" : Number(e.target.value))} style={{ minWidth: 300, flex: 1 }}>
                <option value="">不关联就诊</option>
                {encounters.map((en) => (
                  <option key={en.id} value={en.id}>
                    {en.visit_no || `就诊#${en.id}`}：{(en.chief_complaint || "").slice(0, 30)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <div className="muted" style={{ marginBottom: 10, fontWeight: 500, fontSize: 13 }}>
              病情描述 / 会诊内容
            </div>
            <textarea
              rows={5} style={{ width: "100%" }} value={text}
              placeholder="描述患者症状、病程、既往史、已有检查结果等（生产模式下必填）"
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <div className="muted" style={{ marginBottom: 10, fontWeight: 500, fontSize: 13 }}>
              会诊专科
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              {Object.entries(SPECIALTIES).map(([k, v]) => (
                <button key={k} className={`btn sm ${specs.includes(k as SpecialtyKey) ? "primary" : ""}`} onClick={() => toggleSpec(k as SpecialtyKey)}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <div className="muted" style={{ marginBottom: 10, fontWeight: 500, fontSize: 13 }}>
              技能包
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
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

          <div style={{ marginBottom: 20 }}>
            <div className="muted" style={{ marginBottom: 10, fontWeight: 500, fontSize: 13 }}>
              引用文档（可选）
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              {docs.map((d) => (
                <button key={d.id} className={`btn sm ${selDocs.includes(d.id) ? "primary" : ""}`}
                  onClick={() => setSelDocs((p) => (p.includes(d.id) ? p.filter((x) => x !== d.id) : [...p, d.id]))}>
                  {d.name}
                </button>
              ))}
              {docs.length === 0 && <span className="muted">暂无文档（可在知识库上传）</span>}
            </div>
          </div>

          <div className="row" style={{ marginTop: 24, paddingTop: 20, borderTop: "2px solid #e2e8f0", gap: 16, alignItems: "center" }}>
            <select value={style} onChange={(e) => setStyle(e.target.value as "brief" | "detailed" | "evidence")} style={{ minWidth: 140 }}>
              <option value="brief">简要风格</option>
              <option value="detailed">详细风格</option>
              <option value="evidence">循证风格</option>
            </select>
            <select value={rounds} onChange={(e) => setRounds(Number(e.target.value))} style={{ minWidth: 160 }}>
              <option value={1}>1 轮（独立意见）</option>
              <option value={2}>2 轮（交叉讨论）</option>
              <option value={3}>3 轮（深入讨论）</option>
            </select>
            <div className="muted" style={{ flex: 1, fontSize: 12.5, textAlign: "center" }}>
              ⚙️ 更多设置（LLM、技能包、模式）请在「系统设置」中配置
            </div>
            <button className="btn primary lg" disabled={busy} onClick={create}>
              <span>{busy ? "⏳ 会诊进行中…" : "🚀 发起会诊"}</span>
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
            <tr><th>标题</th><th>模式</th><th>状态</th><th>完备度</th><th>时间</th><th></th></tr>
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
                <td>
                  <button
                    className="btn xs danger-outline"
                    title="删除本会诊（仅创建者或管理员）"
                    onClick={(e) => { e.stopPropagation(); void removeConsult(c.id, c.title); }}
                  >
                    🗑
                  </button>
                </td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr><td colSpan={6} className="empty">暂无会诊记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {detail && <DetailPanel detail={detail} onClose={() => setDetail(null)} followupText={followupText} setFollowupText={setFollowupText} followBusy={followBusy} followup={followup} />}
      {showLiveModal && liveConsultId && (
        <LiveConsultModal
          consultationId={liveConsultId}
          title={liveConsultTitle}
          onClose={() => setShowLiveModal(false)}
          onViewDetails={() => {
            openDetail(liveConsultId);
            setShowLiveModal(false);
          }}
        />
      )}
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
