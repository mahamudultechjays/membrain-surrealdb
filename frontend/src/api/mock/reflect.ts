import { mockAskApi } from '@/api/mock/ask'
import { traceId } from '@/api/mock/backend'
import type { ReflectApi, ReflectLayer } from '@/api/reflect'

/**
 * Reflection on top of the mock recall, once per layer like the backend: each
 * layer's top hits summed up and listed as its evidence, then org > team >
 * personal applied (the first layer with evidence applies).
 */
export const mockReflectApi: ReflectApi = {
  async ask({ question, scopes = [] }, signal) {
    const answer = await mockAskApi.ask({ q: question, scopes }, signal)
    let winner: string | null = null
    const layers: ReflectLayer[] = answer.layers.map((layer) => {
      const evidence = layer.facts.slice(0, 3).map((fact) => fact.fact)
      const status = !evidence.length ? 'empty' : winner ? 'overridden' : 'applies'
      if (status === 'applies') winner = layer.area
      return {
        layer: layer.layer,
        scope: layer.area,
        status,
        answer: evidence.length
          ? `In this layer, the clearest point is: ${evidence[0]}.`
          : 'Nothing in this layer bears on the question.',
        evidence,
        error: null,
        trace_id: traceId(),
      }
    })
    return { layers, applies: winner, scopes: answer.scopes }
  },
}
