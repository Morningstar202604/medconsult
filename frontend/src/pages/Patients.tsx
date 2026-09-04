import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Encounter, Patient } from "../types";

export default function Patients() {
  const [items, setItems] = useState<Patient[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [selPid, setSelPid] = useState<number | null>(null);

  const [form, setForm] = useState({ name: "", gender: "男", birth_date: "", id_card: "", phone: "", hospital_no: "" });
  const [encForm, setEncForm] = useState({ visit_no: "", chief_complaint: "", history: "", meds: "", exams: "", vitals: "" });

  function maskPhone(phone: string): string {
    if (!phone || phone.length < 7) return phone || "—";
    return phone.slice(0, 3) + "****" + phone.slice(-4);
  }

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ items: Patient[] }>("/api/patients" + (q ? `?q=${encodeURIComponent(q)}` : ""));
      setItems(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, [q]);

  useEffect(() => {
    load();
  }, [load]);

  async function createPatient() {
    try {
      await api.post("/api/patients", form);
      setForm({ name: "", gender: "男", birth_date: "", id_card: "", phone: "", hospital_no: "" });
      setShowCreate(false);
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  async function openPatient(pid: number) {
    setSelPid(pid);
    try {
      const d = await api.get<{ items: Encounter[] }>(`/api/patients/${pid}/encounters`);
      setEncounters(d.items);
    } catch {
      setEncounters([]);
    }
  }

  async function addEncounter() {
    if (!selPid) return;
    try {
      await api.post(`/api/patients/${selPid}/encounters`, encForm);
      setEncForm({ visit_no: "", chief_complaint: "", history: "", meds: "", exams: "", vitals: "" });
      openPatient(selPid);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  return (
    <div>
      <div className="row spread">
        <div>
          <h1 className="page">患者管理</h1>
          <p className="sub">患者与就诊记录（敏感字段加密存储，仅授权人员可见）</p>
        </div>
        <button className="btn primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "收起" : "＋ 建档"}
        </button>
      </div>
      {err && <div className="flag-banner">{err}</div>}

      {showCreate && (
        <div className="panel">
          <div className="row">
            <input type="text" placeholder="姓名" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
              <option>男</option><option>女</option><option>未知</option>
            </select>
            <input type="text" placeholder="出生日期" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} />
            <input type="text" placeholder="住院号/就诊号" value={form.hospital_no} onChange={(e) => setForm({ ...form, hospital_no: e.target.value })} />
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <input type="text" placeholder="身份证号（加密）" value={form.id_card} onChange={(e) => setForm({ ...form, id_card: e.target.value })} />
            <input type="text" placeholder="电话（加密）" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <button className="btn primary" onClick={createPatient}>保存</button>
          </div>
        </div>
      )}

      <div className="panel" style={{ padding: 10 }}>
        <div className="row" style={{ padding: "2px 8px 10px" }}>
          <input className="flex" type="text" placeholder="按住院号搜索…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <table className="tbl">
          <thead><tr><th>ID</th><th>姓名</th><th>性别</th><th>出生日期</th><th>住院号</th><th>电话</th></tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id} style={{ cursor: "pointer" }} onClick={() => openPatient(p.id)}>
                <td>{p.id}</td><td>{p.name}</td><td>{p.gender}</td><td>{p.birth_date}</td>
                <td>{p.hospital_no}</td><td className="muted">{p.phone ? maskPhone(p.phone) : "—"}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="empty">暂无患者</td></tr>}
          </tbody>
        </table>
      </div>

      {selPid != null && (
        <div className="panel">
          <div className="row spread">
            <h1 className="page" style={{ fontSize: 16 }}>就诊记录</h1>
            <button className="btn sm" onClick={() => setSelPid(null)}>关闭</button>
          </div>
          <div className="row" style={{ margin: "10px 0" }}>
            <input type="text" placeholder="就诊号" value={encForm.visit_no} onChange={(e) => setEncForm({ ...encForm, visit_no: e.target.value })} />
            <input className="flex" type="text" placeholder="主诉" value={encForm.chief_complaint} onChange={(e) => setEncForm({ ...encForm, chief_complaint: e.target.value })} />
            <button className="btn primary" onClick={addEncounter}>添加就诊</button>
          </div>
          <textarea className="flex" rows={2} placeholder="现病史" style={{ width: "100%", marginBottom: 6 }} value={encForm.history} onChange={(e) => setEncForm({ ...encForm, history: e.target.value })} />
          <div className="row">
            <input className="flex" type="text" placeholder="用药/过敏" value={encForm.meds} onChange={(e) => setEncForm({ ...encForm, meds: e.target.value })} />
            <input className="flex" type="text" placeholder="辅助检查" value={encForm.exams} onChange={(e) => setEncForm({ ...encForm, exams: e.target.value })} />
            <input className="flex" type="text" placeholder="生命体征" value={encForm.vitals} onChange={(e) => setEncForm({ ...encForm, vitals: e.target.value })} />
          </div>
          <table className="tbl" style={{ marginTop: 10 }}>
            <thead><tr><th>就诊号</th><th>主诉</th><th>现病史</th><th>用药</th><th>检查</th><th>体征</th></tr></thead>
            <tbody>
              {encounters.map((en) => (
                <tr key={en.id}>
                  <td>{en.visit_no}</td><td>{en.chief_complaint}</td><td className="muted">{en.history}</td>
                  <td className="muted">{en.meds}</td><td className="muted">{en.exams}</td><td className="muted">{en.vitals}</td>
                </tr>
              ))}
              {encounters.length === 0 && <tr><td colSpan={6} className="empty">暂无就诊记录</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
