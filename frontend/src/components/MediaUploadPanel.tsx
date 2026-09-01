import { useState } from "react";
import { ApiError, uploadMedia } from "../api";
import type { MediaAsset } from "../types";

/** 多模态上传面板：图片 OCR / 音频 ASR，结果可填入病情描述。
 *  无多模态模型时走本地 OCR/ASR 工具兜底，有配置时走用户自填的 API。 */
export function MediaUploadPanel({ onText }: { onText: (text: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<MediaAsset | null>(null);

  async function handleUpload(file: File, kind: "image" | "audio") {
    setBusy(true);
    setErr("");
    setResult(null);
    try {
      const path = kind === "image" ? "/api/media/ocr" : "/api/media/asr";
      const data = (await uploadMedia(path, file)) as unknown as MediaAsset;
      setResult(data);
      if (data.text && !data.error_msg) onText(data.text);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel" style={{ marginTop: 12, padding: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>
        📎 图片/语音识别（无多模态模型时用 OCR/ASR 工具兜底）
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        上传检查报告/处方/化验单图片自动 OCR，或上传口述问诊/录音会诊音频自动转写；识别结果可一键填入下方病情描述。
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <label className="btn" style={{ cursor: "pointer" }}>
          🖼️ 上传图片 OCR
          <input
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f, "image");
              e.target.value = "";
            }}
          />
        </label>
        <label className="btn" style={{ cursor: "pointer" }}>
          🎙️ 上传音频转写
          <input
            type="file"
            accept="audio/*,video/*"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f, "audio");
              e.target.value = "";
            }}
          />
        </label>
        {busy && <span className="muted">识别中…（首次使用本地引擎可能需下载模型）</span>}
      </div>
      {err && <div style={{ color: "var(--danger)", marginTop: 8, fontSize: 13 }}>{err}</div>}
      {result && (
        <div
          style={{
            marginTop: 10,
            padding: 10,
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          <div className="row" style={{ gap: 8, alignItems: "center", marginBottom: 6 }}>
            <span className="badge production">{result.kind === "image" ? "OCR" : "ASR"}</span>
            <span className="muted" style={{ fontSize: 12 }}>
              {result.filename} · 引擎 {result.engine} · 置信度 {result.confidence}
            </span>
          </div>
          {result.error_msg ? (
            <div style={{ color: "var(--danger)", fontSize: 13 }}>识别失败：{result.error_msg}</div>
          ) : (
            <>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: 13,
                  margin: "6px 0",
                  maxHeight: 200,
                  overflow: "auto",
                }}
              >
                {result.text}
              </pre>
              <button className="btn small" onClick={() => onText(result.text)}>
                填入病情描述
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
