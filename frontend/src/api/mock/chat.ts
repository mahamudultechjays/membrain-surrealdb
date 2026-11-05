import type { ChatApi, ChatCitation } from '@/api/chat'
import { ApiError } from '@/api/client'
import { mockAskApi } from '@/api/mock/ask'
import { currentUser, newId, traceId } from '@/api/mock/backend'

/** Session id -> the email it belongs to, like the backend's ChatSessions. */
const sessions = new Map<string, string>()

/**
 * Chat on top of the mock recall: the same scopes and records, with the top
 * hits stitched into a reply that cites each one as [S1], [S2], ...
 */
export const mockChatApi: ChatApi = {
  async send({ message, session_id, scopes = [] }, signal) {
    const me = currentUser()
    if (session_id && sessions.get(session_id) !== me.email) {
      throw new ApiError(404, 'No such chat session for this user.')
    }
    const answer = await mockAskApi.ask({ q: message, scopes }, signal)
    const hits = answer.layers
      .flatMap((layer) => layer.facts.map((fact) => ({ ...fact, layer })))
      .sort((a, b) => b.source.score - a.source.score)
      .slice(0, 3)
    const citations: ChatCitation[] = hits.map((hit, i) => ({
      marker: `S${i + 1}`,
      id: hit.source.hit_id,
      kind: hit.source.hit_kind,
      snippet: hit.source.text,
      score: hit.source.score,
      document_title: hit.source.kind === 'document' ? 'Mock document' : null,
      position_percent: null,
      role: null,
      occurred_at: null,
      layer: hit.layer.layer,
      scope: hit.layer.area,
    }))
    const reply = citations.length
      ? `From what memory holds: ${citations.map((c) => `${c.snippet} [${c.marker}]`).join('; ')}.`
      : "I couldn't find anything in your spaces about that."
    const session = session_id ?? newId('session')
    sessions.set(session, me.email)
    return {
      reply,
      session_id: session,
      scopes: answer.scopes,
      citations,
      facts_saved: 0,
      trace_id: traceId(),
    }
  },
}
