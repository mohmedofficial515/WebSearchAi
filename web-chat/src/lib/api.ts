// Typed fetch wrappers — no Axios dependency (G13).

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(
      res.status,
      (body as { detail?: string }).detail ?? res.statusText,
    );
  }
  return res.json() as Promise<T>;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  return handleResponse<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(path, { method: 'POST', body: form });
  return handleResponse<T>(res);
}

export function makeWs(taskId: string): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return new WebSocket(`${proto}://${location.host}/ws/${taskId}`);
}

// Response shapes

export interface IntentResponse {
  intent: string;
  confidence: number;
  missing_params?: string[];
  is_compound?: boolean;
}

export interface ChatResponse {
  mode: 'single' | 'pipeline' | 'need_params' | 'approved';
  task_id?: string;
  pipeline_id?: string;
  missing_params?: string[];
}

export interface UploadResponse {
  attachment_id: string;
  url: string;
  mime: string;
  size: number;
}
