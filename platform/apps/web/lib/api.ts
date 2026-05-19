const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as any),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(`${API}${path}`, { ...init, headers });
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
}

export const Api = {
  register: (email: string, password: string) =>
    api<{ access_token: string; user_id: string; credits: number }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    api<{ access_token: string; user_id: string; credits: number }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => api<{ id: string; email: string; credits: number }>("/api/v1/users/me"),
  presign: (contentType: string) =>
    api<{ upload_url: string; key: string; public_url: string }>(
      `/api/v1/uploads/presign?content_type=${encodeURIComponent(contentType)}`,
      { method: "POST" }
    ),
  createJob: (type: string, model: string | null, input: any) =>
    api<{ id: string; status: string }>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify({ type, model, input }),
    }),
  getJob: (id: string) => api<any>(`/api/v1/jobs/${id}`),
  streamJob(id: string, onEvent: (e: any) => void) {
    const token = getToken();
    const url = `${API}/api/v1/jobs/${id}/stream`;
    const es = new EventSource(url + (token ? `?token=${token}` : ""));
    es.onmessage = (m) => {
      try { onEvent(JSON.parse(m.data)); } catch {}
    };
    return es;
  },
};
