import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { FeedbackItem } from "../types";

export default function Feedback({ user }: { user: { role: string } }) {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(0);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ items: FeedbackItem[] }>("/api/feedback" + (filter ? `?status=${filter}` : ""));
      setItems(d.items);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function review(id: number, approve: boolean) {
    setBusy(id);
    try {
      await api.post(`/api/feedback/${id}/review`, { approve });
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "审核失败");
    } finally {
      setBusy(0);
    }
  }

  return (
    <div>
      <h1 className="page">反馈审核</h1>
      <p className="sub">
        医生对报告的反馈须经主任/管理员审核通过后，才会纳入后续相似会诊的经验注入（记录来源与审核人，全程留痕）
      </p>
      {err && <div className="flag-banner">{err}</div>}

      <div className="panel" style={{ padding: 10 }}>
        <div className="row" style={{ padding: "2px 8px 10px" }}>
          <button className={`btn sm ${filter === "" ? "primary" : ""}`} onClick={() => setFilter("")}>全部</button>
          <button className={`btn sm ${filter === "pending_review" ? "primary" : ""}`} onClick={() => setFilter("pending_review")}>待审核</button>
          <button className={`btn sm ${filter === "approved" ? "primary" : ""}`} onClick={() => setFilter("approved")}>已通过</button>
          <button className={`btn sm ${filter === "rejected" ? "primary" : ""}`} onClick={() => setFilter("rejected")}>已驳回</button>
        </div>

        {items.map((f) => (
          <div key={f.id} className="panel" style={{ marginBottom: 12 }}>
            <div className="row spread">
              <div className="row">
                <span className={`badge ${f.status === "pending_review" ? "pending" : f.status === "approved" ? "approved" : "rejected"}`}>
                  {f.status === "pending_review" ? "待审核" : f.status === "approved" ? "已通过" : "已驳回"}
                </span>
                <span className={`badge ${f.helpful ? "approved" : "danger"}`}>{f.helpful ? "有效反馈" : "问题反馈"}</span>
                <span className="muted">提交人：{f.submitted_by}</span>
                {f.reviewed_by && <span className="muted">审核人：{f.reviewed_by} · {f.reviewed_at || ""}</span>}
              </div>
              {f.status === "pending_review" && (
                <div className="row">
                  <button className="btn sm primary" disabled={busy === f.id} onClick={() => review(f.id, true)}>通过并纳入经验</button>
                  <button className="btn sm danger" disabled={busy === f.id} onClick={() => review(f.id, false)}>驳回</button>
                </div>
              )}
            </div>
            <div style={{ marginTop: 8 }}>
              <b>{f.title}</b>
              <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{f.diagnosis}</div>
              {f.note && <div style={{ marginTop: 6 }}>💬 {f.note}</div>}
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="empty">暂无反馈记录</div>}
      </div>
    </div>
  );
}
