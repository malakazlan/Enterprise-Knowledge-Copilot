/** API response shapes — mirrors backend/app/schemas. */

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserRead {
  id: string;
  email: string;
  full_name: string | null;
  role: "admin" | "reviewer" | "user";
  is_active: boolean;
  created_at: string;
}

export interface DocumentRead {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  status: "pending" | "processing" | "completed" | "failed";
  title: string | null;
  page_count: number | null;
  doc_metadata: Record<string, unknown>;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueryCitation {
  marker: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  title: string | null;
  page_number: number | null;
  snippet: string;
}

export interface QueryResponse {
  query_id: string;
  query: string;
  profile: string;
  answer: string | null;
  answered: boolean;
  refusal_reason: string | null;
  citations: QueryCitation[];
  confidence: number;
  confidence_breakdown: Record<string, number>;
  grounded_ratio: number;
  needs_review: boolean;
  model: string;
  sources_considered: number;
  retrieval_took_ms: number;
  took_ms: number;
}

export interface ProfileSummary {
  name: string;
  description?: string;
}

export interface ReviewItem {
  id: string;
  query: string;
  answer: string | null;
  profile: string;
  confidence: number;
  grounded_ratio: number;
  model: string;
  citations: Record<string, unknown>[];
  review_status: "pending" | "approved" | "rejected" | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AdminStats {
  documents_total: number;
  documents_failed: number;
  chunks_total: number;
  queries_total: number;
  queries_answered: number;
  queries_refused: number;
  refusal_breakdown: Record<string, number>;
  avg_confidence_answered: number | null;
  reviews_pending: number;
  api_keys_active: number;
  users_total: number;
}

export interface ChunkRead {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  token_count: number | null;
}

export interface ApiKeyRead {
  id: string;
  name: string;
  role: "admin" | "reviewer" | "user";
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  role: string;
  key: string;
  key_prefix: string;
  expires_at: string | null;
  created_at: string;
}
