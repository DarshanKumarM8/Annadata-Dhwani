// Owner: Darshan. Shared fetch wrapper (contract: TASK_DIVISION.md §11, P0).
//   api.get(path), api.post(path, body, extraHeaders?), api.postForm(path, formData)
// Adds "Authorization: Bearer <token>" from localStorage "token".
// On non-2xx it throws ApiError with .status and .body (parsed JSON such as {"error":"CODE", ...}).

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8001";
export const WS_BASE: string = import.meta.env.VITE_WS_BASE ?? "ws://localhost:8001";

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any) {
    super(body?.error ? `${status} ${body.error}` : `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem("token");
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem("token", token);
    else localStorage.removeItem("token");
  } catch {
    /* storage blocked: nothing to do */
  }
}

async function request(method: string, path: string, body?: BodyInit, headers: Record<string, string> = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    body,
    headers: {
      "ngrok-skip-browser-warning": "true",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: "NON_JSON_RESPONSE", raw: text };
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const api = {
  get: (path: string) => request("GET", path),
  post: (path: string, json?: unknown, extraHeaders: Record<string, string> = {}) =>
    request("POST", path, json === undefined ? undefined : JSON.stringify(json), {
      "Content-Type": "application/json",
      ...extraHeaders,
    }),
  postForm: (path: string, form: FormData) => request("POST", path, form),
};

/** Absolute URL for a server-relative path such as "/audio/mix/x.wav" or "/media/v/x.jpg". */
export const absUrl = (p: string) => (p.startsWith("http") ? p : `${API_BASE}${p}`);