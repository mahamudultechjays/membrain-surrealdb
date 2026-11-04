import { apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockChatApi } from '@/api/mock/chat'

// Mirrors backend/app/schemas/chat.py.

export interface ChatCitation {
  /** The marker as written in the reply, without brackets: "S1" for "[S1]". */
  marker: string
  id: string
  /** attribute, entity, relation, turn, chunk, section, ... */
  kind: string
  snippet: string
  /** Retrieval match score for this question, not trust. */
  score: number
  document_title: string | null
  position_percent: number | null
  /** "assistant" when the source is an earlier stored reply, not a fact. */
  role: string | null
  occurred_at: string | null
}

export interface ChatResponse {
  reply: string
  /** Send back to continue this conversation. */
  session_id: string
  /** The scopes the answer could draw on. */
  scopes: string[]
  citations: ChatCitation[]
  /** Entities, attributes and relations Agent Memory extracted from the message. */
  facts_saved: number
  trace_id: string | null
}

export interface ChatRequest {
  message: string
  /** Null starts a new conversation. */
  session_id: string | null
  /** Narrows the readable scopes; empty reads them all. */
  scopes?: string[]
}

export interface ChatApi {
  send(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse>
}

export const httpChatApi: ChatApi = {
  send: (request, signal) =>
    apiPost<ChatResponse>('/api/v1/ask/chat', request, { signal }),
}

export const chatApi: ChatApi = USE_MOCK_API ? mockChatApi : httpChatApi
