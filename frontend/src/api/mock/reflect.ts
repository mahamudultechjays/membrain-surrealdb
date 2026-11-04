import { mockAskApi } from '@/api/mock/ask'
import { traceId } from '@/api/mock/backend'
import type { ReflectApi } from '@/api/reflect'

/**
 * Reflection on top of the mock recall: the same scopes and records, with the
 * top hits summed up in one paragraph and listed as evidence.
 */
export const mockReflectApi: ReflectApi = {
  async ask({ question, scopes = [] }, signal) {
    const answer = await mockAskApi.ask({ q: question, scopes }, signal)
    const evidence = answer.layers
      .flatMap((layer) => layer.facts)
      .sort((a, b) => b.source.score - a.source.score)
      .slice(0, 4)
      .map((fact) => fact.fact)
    return {
      answer: evidence.length
        ? `Across your spaces, the clearest pattern is: ${evidence[0]}. ${
            evidence.length > 1
              ? `It sits alongside ${evidence.length - 1} related memories.`
              : ''
          }`.trim()
        : 'Your spaces hold nothing that bears on this question.',
      evidence,
      scopes: answer.scopes,
      trace_id: traceId(),
    }
  },
}
