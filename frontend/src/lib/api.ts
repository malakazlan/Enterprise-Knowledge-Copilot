/** Typed API client: bearer auth in sessionStorage, single-flight refresh on 401. */

import type {
  AdminStats,
  ApiKeyCreated,
  ApiKeyRead,
  ChunkRead,
  CollectionMemberRead,
  CollectionRead,
  ConnectorRead,
  DocumentRead,
  EvalCaseRead,
  EvalDatasetDetail,
  EvalDatasetRead,
  EvalRunRead,
  FolderSyncReport,
  ProfileSummary,
  QueryResponse,
  ReviewItem,
  SearchResponse,
  ThreadDetail,
  ThreadRead,
  TokenPair,
  WebhookRead,
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

export function adoptTokens(access: string, refresh: string): void {
  storeTokens({ access_token: access, refresh_token: refresh, token_type: "bearer" });
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

export function uploadDocument(file: File, collectionId?: string | null): Promise<DocumentRead> {
  const form = new FormData();
  form.append("file", file);
  const suffix = collectionId ? `?collection_id=${collectionId}` : "";
  return request<DocumentRead>(`/documents${suffix}`, { method: "POST", form });
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

// ---- search & team ----

export const searchChunks = (query: string, topK = 8): Promise<SearchResponse> =>
  request<SearchResponse>("/search", { method: "POST", json: { query, top_k: topK } });

export const listUsers = (): Promise<UserRead[]> => request<UserRead[]>("/users?limit=200");

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

// ---- chunks & keys ----

export const getDocument = (id: string): Promise<DocumentRead> =>
  request<DocumentRead>(`/documents/${id}`);

export const listChunks = (documentId: string): Promise<ChunkRead[]> =>
  request<ChunkRead[]>(`/documents/${documentId}/chunks`);

export const listApiKeys = (): Promise<ApiKeyRead[]> => request<ApiKeyRead[]>("/api-keys");

export const createApiKey = (name: string, role: string): Promise<ApiKeyCreated> =>
  request<ApiKeyCreated>("/api-keys", { method: "POST", json: { name, role } });

export const revokeApiKey = (id: string): Promise<void> =>
  request<void>(`/api-keys/${id}`, { method: "DELETE" });

// ---- integrations ----

export const listWebhooks = (): Promise<WebhookRead[]> =>
  request<WebhookRead[]>("/admin/webhooks");

export const createWebhook = (
  url: string,
  events: string[],
  secret: string | null,
): Promise<WebhookRead> =>
  request<WebhookRead>("/admin/webhooks", {
    method: "POST",
    json: secret ? { url, events, secret } : { url, events },
  });

export const deleteWebhook = (id: string): Promise<void> =>
  request<void>(`/admin/webhooks/${id}`, { method: "DELETE" });

export const syncFolder = (path: string): Promise<FolderSyncReport> =>
  request<FolderSyncReport>("/connectors/folder/sync", { method: "POST", json: { path } });

// ---- threads & streaming ----

export const listThreads = (): Promise<ThreadRead[]> => request<ThreadRead[]>("/threads");

export const createThread = (): Promise<ThreadRead> =>
  request<ThreadRead>("/threads", { method: "POST", json: {} });

export const getThread = (id: string): Promise<ThreadDetail> =>
  request<ThreadDetail>(`/threads/${id}`);

export const deleteThread = (id: string): Promise<void> =>
  request<void>(`/threads/${id}`, { method: "DELETE" });

/** Stream a verified answer. Calls onToken as text arrives, resolves with the
 *  final QueryResponse from the `result` event. */
export async function streamQuery(
  query: string,
  profile: string | null,
  threadId: string | null,
  onToken: (text: string) => void,
): Promise<QueryResponse> {
  const token = getAccessToken();
  const res = await fetch(`${V1}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      query,
      ...(profile ? { profile } : {}),
      ...(threadId ? { thread_id: threadId } : {}),
    }),
  });
  if (!res.ok || !res.body) throw await parseError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";
  let result: QueryResponse | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("event: ")) eventName = line.slice(7).trim();
      else if (line.startsWith("data: ")) {
        const data: unknown = JSON.parse(line.slice(6));
        if (eventName === "token") onToken((data as { text: string }).text);
        else if (eventName === "result") result = data as QueryResponse;
      }
    }
  }
  if (!result) throw new ApiError(502, "Stream ended without a result.");
  return result;
}

// ---- collections ----

export const listCollections = (): Promise<CollectionRead[]> =>
  request<CollectionRead[]>("/collections");

export const createCollection = (name: string, description: string | null): Promise<CollectionRead> =>
  request<CollectionRead>("/collections", {
    method: "POST",
    json: description ? { name, description } : { name },
  });

export const deleteCollection = (id: string): Promise<void> =>
  request<void>(`/collections/${id}`, { method: "DELETE" });

export const listCollectionMembers = (id: string): Promise<CollectionMemberRead[]> =>
  request<CollectionMemberRead[]>(`/collections/${id}/members`);

export const addCollectionMember = (id: string, email: string): Promise<CollectionMemberRead> =>
  request<CollectionMemberRead>(`/collections/${id}/members`, {
    method: "POST",
    json: { email },
  });

export const removeCollectionMember = (id: string, userId: string): Promise<void> =>
  request<void>(`/collections/${id}/members/${userId}`, { method: "DELETE" });

// ---- sso ----

export const ssoStatus = (): Promise<{ enabled: boolean; provider: string }> =>
  request<{ enabled: boolean; provider: string }>("/auth/oidc/status");

export const SSO_LOGIN_URL = `${V1}/auth/oidc/login`;

// ---- evals ----

export const listEvalDatasets = (): Promise<EvalDatasetRead[]> =>
  request<EvalDatasetRead[]>("/evals/datasets");

export const createEvalDataset = (name: string, profile: string | null): Promise<EvalDatasetRead> =>
  request<EvalDatasetRead>("/evals/datasets", {
    method: "POST",
    json: profile ? { name, profile } : { name },
  });

export const getEvalDataset = (id: string): Promise<EvalDatasetDetail> =>
  request<EvalDatasetDetail>(`/evals/datasets/${id}`);

export const deleteEvalDataset = (id: string): Promise<void> =>
  request<void>(`/evals/datasets/${id}`, { method: "DELETE" });

export const addEvalCase = (
  datasetId: string,
  question: string,
  expectedKeywords: string[],
): Promise<EvalCaseRead> =>
  request<EvalCaseRead>(`/evals/datasets/${datasetId}/cases`, {
    method: "POST",
    json: { question, expected_keywords: expectedKeywords },
  });

export const runEvalDataset = (datasetId: string, profile: string | null): Promise<EvalRunRead> =>
  request<EvalRunRead>(`/evals/datasets/${datasetId}/run`, {
    method: "POST",
    json: profile ? { profile } : {},
  });

export const listEvalRuns = (datasetId: string): Promise<EvalRunRead[]> =>
  request<EvalRunRead[]>(`/evals/datasets/${datasetId}/runs`);

// ---- saved connectors ----

export const listConnectors = (): Promise<ConnectorRead[]> =>
  request<ConnectorRead[]>("/connectors");

export const createConnector = (
  name: string,
  type: string,
  config: Record<string, unknown>,
): Promise<ConnectorRead> =>
  request<ConnectorRead>("/connectors", { method: "POST", json: { name, type, config } });

export const syncConnector = (id: string): Promise<FolderSyncReport> =>
  request<FolderSyncReport>(`/connectors/${id}/sync`, { method: "POST" });

export const deleteConnector = (id: string): Promise<void> =>
  request<void>(`/connectors/${id}`, { method: "DELETE" });

export const connectorAuthorize = (id: string): Promise<{ authorize_url: string }> =>
  request<{ authorize_url: string }>(`/connectors/${id}/authorize`);

export const submitFeedback = (queryId: string, verdict: "helpful" | "unhelpful"): Promise<void> =>
  request<void>(`/query/${queryId}/feedback`, { method: "POST", json: { verdict } });
