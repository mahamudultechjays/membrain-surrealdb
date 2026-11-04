import { apiGet, apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockCaptureApi } from '@/api/mock/capture'

// Mirrors backend/app/schemas/capture.py on feat/capture-ak-scoping-api.

/** triples writes only the kept facts as triples; full re-extracts the whole source. */
export type StoreMode = 'triples' | 'full'
export type MemoryCategory = 'identity' | 'knowledge' | 'context'
export type InputType = 'text' | 'document'

export interface CaptureConfig {
  mode: StoreMode
  memory_category: MemoryCategory | null
}

export interface CapturePreviewRequest {
  /** A scope the signed-in user may write; null means their personal scope. */
  scope: string | null
  input_type: InputType
  config: CaptureConfig
  /** Plain text, or the file's bytes as base64 for a document. */
  content: string
  file_name?: string | null
}

export interface ExtractedFact {
  /** e1, e2, ... unique within one preview. */
  id: string
  /** "entity · key = value", "subject · label → object" or "entity · type = kind". */
  fact: string
  /** The memory category Agent Memory gave it. */
  type: string
  /** "text", or "document <name>" with " (first words)" when truncated. */
  source: string
  /** "uncertain: <reason>", the no-entity note, or null. */
  note: string | null
  /** False: no entity link in the preview, so only full can store it. */
  storable: boolean
  /** No entity link, but the user can pick one of the preview's entities for it. */
  needs_entity: boolean
}

/** An entity the preview found, offered for facts with needs_entity. */
export interface EntityChoice {
  name: string
  entity_type: string
}

export interface CapturePreviewResponse {
  preview_id: string
  scope: string
  extracted: ExtractedFact[]
  /** uncertain counts facts Agent Memory raised an uncertainty about. */
  stats: { total: number; uncertain: number; corrections: number }
  truncated: boolean
  truncated_reason: string | null
  /** Set for documents: the upload to poll with getDocumentStatus. */
  doc_id: string | null
  corrections: string[]
  entities: EntityChoice[]
  trace_id: string | null
}

export interface CaptureStoreRequest {
  preview_id: string
  /** Optional; when given it must match the preview's scope. */
  scope?: string | null
  kept: string[]
  config: CaptureConfig
  /** Fact id -> entity name, for kept facts with needs_entity (triples mode). */
  entity_choices?: Record<string, string>
}

export interface CreatedFact {
  entity: string
  key: string
  value: string
  id: string | null
}

export interface HistoryEntry {
  fact_id: string | null
  key: string | null
  old_value: string | null
  new_value: string | null
  changed_at: string
}

export interface CaptureStoreResponse {
  stored_id: string
  written: number
  created_facts: CreatedFact[]
  history: HistoryEntry[]
  trace_id: string | null
}

/** Mode full in one call: the input only, since there is nothing to review or override. */
export type CaptureExtractRequest = Omit<CapturePreviewRequest, 'config'>

export interface CaptureExtractResponse extends CaptureStoreResponse {
  scope: string
  /** Set for documents: the upload to poll with documentStatus. */
  doc_id: string | null
  /** Large documents are extracted from their first words; the whole file is uploaded. */
  truncated: boolean
  truncated_reason: string | null
}

export interface DocumentStatus {
  doc_id: string
  status: string
  finished: boolean
  chunks: number
  keywords: number
  created_at: string | null
  updated_at: string | null
  message: string
}

/** Backend limits: longer text must go through the document tab. */
export const MAX_TEXT_CHARS = 20_000
export const MAX_FILE_BYTES = 10 * 1024 * 1024
/** Documents over this many words are previewed from their first 500 words. */
export const LARGE_DOCUMENT_WORDS = 2000

export interface CaptureApi {
  preview(
    body: CapturePreviewRequest,
    signal?: AbortSignal,
  ): Promise<CapturePreviewResponse>
  store(body: CaptureStoreRequest, signal?: AbortSignal): Promise<CaptureStoreResponse>
  /** Re-extract everything (mode full): extract and store in one call, no preview. */
  extract(
    body: CaptureExtractRequest,
    signal?: AbortSignal,
  ): Promise<CaptureExtractResponse>
  /** Only the uploader (or an admin) can see a document's status. */
  documentStatus(docId: string, signal?: AbortSignal): Promise<DocumentStatus>
}

export const httpCaptureApi: CaptureApi = {
  preview: (body, signal) =>
    apiPost<CapturePreviewResponse>('/api/v1/capture/preview', body, { signal }),
  store: (body, signal) =>
    apiPost<CaptureStoreResponse>('/api/v1/capture/store', body, { signal }),
  extract: (body, signal) =>
    apiPost<CaptureExtractResponse>('/api/v1/capture/extract', body, { signal }),
  documentStatus: (docId, signal) =>
    apiGet<DocumentStatus>(
      `/api/v1/capture/document/${encodeURIComponent(docId)}/status`,
      { signal },
    ),
}

export const captureApi: CaptureApi = USE_MOCK_API ? mockCaptureApi : httpCaptureApi
