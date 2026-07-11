/** Typed API client: bearer auth in sessionStorage, single-flight refresh on 401. */

import type {
  AdminStats,
  DocumentRead,
  ProfileSummary,
  QueryResponse,
  ReviewItem,
  TokenPair,
  UserRead,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const V1 = `${API_BASE}/api/v1`;

const ACCESS_KEY = "ekc.access";
const REFRESH_KEY = "ekc.refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(ACCESS_KEY);
}

function storeTokens(pair: TokenPair): void {
  sessionStorage.setItem(ACCESS_KEY, pair.access_token);
  sessionStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      if (typeof d === "string") detail = d;
      else detail = JSON.stringify(d);
    }
  } catch {
    // non-JSON error body; keep statusText
  }
  return new ApiError(res.status, detail);
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    const refresh = sessionStorage.getItem(REFRESH_KEY);
    if (!refresh) return false;
    const res = await fetch(`${V1}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) {
      clearTokens();
      return false;
    }
    storeTokens((await res.json()) as TokenPair);
    return true;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: FormData;
}

async function request<T>(path: string, opts: RequestOptions = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.json !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${V1}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.form ?? (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
  });

  if (res.status === 401 && !retried && (await tryRefresh())) {
    return request<T>(path, opts, true);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- auth ----

export async function login(email: string, password: string): Promise<void> {
  const pair = await request<TokenPair>("/auth/login", {
    method: "POST",
    json: { email, password },
  });
  storeTokens(pair);
}

export async function register(
  email: string,
  password: string,
  fullName: string,
): Promise<UserRead> {
  return request<UserRead>("/auth/register", {
    method: "POST",
    json: { email, password, full_name: fullName },
  });
}

export const me = (): Promise<UserRead> => request<UserRead>("/auth/me");

// ---- documents ----

export const listDocuments = (): Promise<DocumentRead[]> =>
  request<DocumentRead[]>("/documents?limit=200");

export function uploadDocument(file: File): Promise<DocumentRead> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentRead>("/documents", { method: "POST", form });
}

export const deleteDocument = (id: string): Promise<void> =>
  request<void>(`/documents/${id}`, { method: "DELETE" });

// ---- query ----

export const runQuery = (query: string, profile: string | null): Promise<QueryResponse> =>
  request<QueryResponse>("/query", {
    method: "POST",
    json: profile ? { query, profile } : { query },
  });

export const listProfiles = (): Promise<ProfileSummary[]> =>
  request<ProfileSummary[]>("/profiles");

// ---- reviews & admin ----

export const listReviews = (status: string): Promise<ReviewItem[]> =>
  request<ReviewItem[]>(`/reviews?status=${encodeURIComponent(status)}`);

export const resolveReview = (
  id: string,
  action: "approve" | "reject",
  note: string,
): Promise<ReviewItem> =>
  request<ReviewItem>(`/reviews/${id}/resolve`, {
    method: "POST",
    json: note ? { action, note } : { action },
  });

export const adminStats = (): Promise<AdminStats> => request<AdminStats>("/admin/stats");
