// API 客户端：JWT 令牌管理 + 统一请求封装
const TOKEN_KEY = "mc_token";
const USER_KEY = "mc_user";

export interface Me {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "chief" | "doctor";
  hospital?: string;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setAuth(token: string, user: Me) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
export function getUser(): Me | null {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    clearAuth();
    window.location.hash = "#/login";
    throw new ApiError(401, "登录已过期");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (data as { detail?: string }).detail || `请求失败(${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  del: <T>(path: string, body?: unknown) => request<T>("DELETE", path, body),
};

// SSE 流式消费：fetch + ReadableStream 解析（可携带 Authorization 头）
export async function streamSSE(
  path: string,
  handlers: { onEvent?: (event: string, data: unknown) => void; onDone?: () => void }
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { headers });
  if (!res.ok || !res.body) throw new ApiError(res.status, "流式连接失败");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const lines = raw.split("\n");
        const ev = (lines.find((l) => l.startsWith("event:")) || "").slice(6).trim() || "message";
        const dataLine = (lines.find((l) => l.startsWith("data:")) || "").slice(5).trim();
        if (!dataLine) continue;
        try {
          handlers.onEvent?.(ev, JSON.parse(dataLine));
        } catch {
          /* 忽略非法帧 */
        }
      }
    }
  } finally {
    reader.releaseLock();
    handlers.onDone?.();
  }
}

export function copyText(text: string): boolean {
  try {
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fallthrough */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
}

// 多模态上传（OCR/ASR），multipart/form-data
export async function uploadMedia(
  path: string,
  file: File,
  extra: Record<string, string> = {}
): Promise<Record<string, unknown>> {
  const token = getToken();
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(extra).forEach(([k, v]) => {
    if (v !== "" && v != null) fd.append(k, String(v));
  });
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { method: "POST", headers, body: fd });
  if (res.status === 401) {
    clearAuth();
    window.location.hash = "#/login";
    throw new ApiError(401, "登录已过期");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (data as { detail?: string }).detail || `上传失败(${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data as Record<string, unknown>;
}
