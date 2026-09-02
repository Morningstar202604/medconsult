import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Doc, Skill } from "../types";

interface RefItem { item: string; en: string; unit: string; range: string; note: string; }

export default function Knowledge({ user }: { user?: { role: string } }) {
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<"docs" | "skills" | "ref">("docs");

  return (
    <div>
      <h1 className="page">知识库</h1>
      <p className="sub">会诊参考资料：文档库（检索注入）、技能包（专科指令）、检验参考值（内置校验）</p>
      <div className="toolbar">
        <button className={`btn sm ${tab === "docs" ? "primary" : ""}`} onClick={() => setTab("docs")}>文档库</button>
        <button className={`btn sm ${tab === "skills" ? "primary" : ""}`} onClick={() => setTab("skills")}>技能包</button>
        <button className={`btn sm ${tab === "ref" ? "primary" : ""}`} onClick={() => setTab("ref")}>检验参考值</button>
      </div>
      {tab === "docs" && <DocsTab isAdmin={isAdmin} />}
      {tab === "skills" && <SkillsTab isAdmin={isAdmin} />}
      {tab === "ref" && <RefTab isAdmin={isAdmin} />}
    </div>
  );
}

function DocsTab({ isAdmin }: { isAdmin: boolean }) {
  const [items, setItems] = useState<Doc[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ items: Doc[] }>("/api/library");
      setItems(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setErr("");
    try {
      const fd = new FormData();
      for (const f of Array.from(files)) fd.append("files", f);
      const res = await fetch("/api/library/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("mc_token") || ""}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) setErr((data as { detail?: string }).detail || "上传失败");
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function del(id: number) {
    try {
      await api.del(`/api/library/${id}`);
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "删除失败");
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 12 }}>
        <input type="file" multiple accept=".txt,.md,.pdf,.docx,.json,.csv,.log,.xml"
          onChange={(e) => upload(e.target.files)} disabled={busy} />
        <span className="muted">支持 txt/md/pdf/docx/json/csv/log/xml，单文件 ≤ 32MB，上传后自动建立检索索引</span>
      </div>
      {err && <div className="flag-banner">{err}</div>}
      <table className="tbl">
        <thead><tr><th>文件名</th><th>类型</th><th>大小</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td className="muted">{d.ext}</td>
              <td className="muted">{(d.size / 1024).toFixed(1)} KB</td>
              <td><button className="btn sm danger" onClick={() => del(d.id)}>删除</button></td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={4} className="empty">暂无文档</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function SkillsTab({ isAdmin }: { isAdmin: boolean }) {
  const [items, setItems] = useState<Skill[]>([]);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ name: "", desc: "", prompt: "" });

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ items: Skill[] }>("/api/skills");
      setItems(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    try {
      await api.post("/api/skills", form);
      setForm({ name: "", desc: "", prompt: "" });
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  async function del(id: number) {
    try {
      await api.del(`/api/skills/${id}`);
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "删除失败");
    }
  }

  return (
    <div className="panel">
      {isAdmin && (
        <div className="panel" style={{ background: "#f8fafc" }}>
          <div className="muted" style={{ marginBottom: 6 }}>新增技能包（写入会诊的专科指令模板）</div>
          <div className="row">
            <input type="text" placeholder="名称（如：抗凝管理）" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="flex" type="text" placeholder="简介" value={form.desc} onChange={(e) => setForm({ ...form, desc: e.target.value })} />
          </div>
          <textarea rows={2} style={{ width: "100%", margin: "8px 0" }} placeholder="指令正文（专科审查要求）" value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} />
          <button className="btn primary" onClick={create}>保存技能包</button>
        </div>
      )}
      {err && <div className="flag-banner">{err}</div>}
      {items.map((s) => (
        <div key={s.id} className="panel" style={{ marginBottom: 10 }}>
          <div className="row spread">
            <b>{s.name}</b>
            {isAdmin && <button className="btn sm danger" onClick={() => del(s.id)}>删除</button>}
          </div>
          <div className="muted">{s.desc}</div>
          <div style={{ marginTop: 6, fontSize: 12.5, color: "var(--text-2)", background: "#f8fafc", padding: 8, borderRadius: 8, whiteSpace: "pre-wrap" }}>{s.prompt}</div>
        </div>
      ))}
    </div>
  );
}

function RefTab({ isAdmin }: { isAdmin: boolean }) {
  const [items, setItems] = useState<RefItem[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ item: "", en: "", unit: "", range: "", note: "" });

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ items: RefItem[] }>("/api/reference" + (q ? `?q=${encodeURIComponent(q)}` : ""));
      setItems(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, [q]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    try {
      await api.post("/api/reference", form);
      setForm({ item: "", en: "", unit: "", range: "", note: "" });
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    }
  }

  async function del(item: string) {
    try {
      await api.del("/api/reference", { item });
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "删除失败");
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ marginBottom: 10 }}>
        <input className="flex" type="text" placeholder="搜索检验项…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {isAdmin && (
        <div className="panel" style={{ background: "#f8fafc" }}>
          <div className="row">
            <input type="text" placeholder="检验项" value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} />
            <input type="text" placeholder="英文" value={form.en} onChange={(e) => setForm({ ...form, en: e.target.value })} />
            <input type="text" placeholder="单位" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
            <input type="text" placeholder="参考范围" value={form.range} onChange={(e) => setForm({ ...form, range: e.target.value })} />
            <button className="btn primary" onClick={create}>添加</button>
          </div>
        </div>
      )}
      {err && <div className="flag-banner">{err}</div>}
      <table className="tbl">
        <thead><tr><th>检验项</th><th>英文</th><th>单位</th><th>参考范围</th><th>备注</th>{isAdmin && <th></th>}</tr></thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.item}>
              <td>{r.item}</td><td className="muted">{r.en}</td><td>{r.unit}</td><td>{r.range}</td>
              <td className="muted">{r.note}</td>
              {isAdmin && <td><button className="btn sm danger" onClick={() => del(r.item)}>删除</button></td>}
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={6} className="empty">暂无检验参考项</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
