import type { BrainApi, BrainChunk, BrainEntity } from '@/api/brain'
import { ApiError } from '@/api/client'
import { MOCK_ADMINS, currentUser, delay, records } from '@/api/mock/backend'

// The seed's facts are "entity · key = value"; documents (chunks) have no entity.
const FACT = /^(.+?) · (.+?) = (.+)$/

/** A stable, spread-out timestamp per record, oldest first, for the date filters. */
const stamp = (index: number) =>
  new Date(Date.UTC(2026, 9, 1) + index * 36 * 3600 * 1000).toISOString()

export const mockBrainApi: BrainApi = {
  async list({ scopes = [], subscopes = false }, signal) {
    await delay(300, signal)
    const me = currentUser()
    const allowed = MOCK_ADMINS.has(me.email)
      ? null
      : new Set(me.grants.map((g) => g.scope_path))
    const missing = allowed ? scopes.filter((s) => !allowed.has(s)) : []
    if (missing.length) throw new ApiError(403, `Not readable: ${missing.join(', ')}`)

    const visible = (path: string) => !allowed || allowed.has(path)
    const wanted = (path: string) =>
      !scopes.length ||
      scopes.some((s) => path === s || (subscopes && path.startsWith(s + '/')))

    const byName = new Map<string, BrainEntity>()
    const chunks: BrainChunk[] = []
    const every = new Set<string>()
    records.forEach((record, index) => {
      const match = record.kind === 'attribute' ? FACT.exec(record.text) : null
      if (!match || !visible(record.area)) return
      every.add(record.area)
      if (!wanted(record.area)) return
      const [, name = '', key = '', value = ''] = match
      const created_at = stamp(index)
      let entity = byName.get(name)
      if (!entity) {
        entity = {
          ref: `concept/${name.replace(/\s+/g, '_')}`,
          name,
          entity_type: 'concept',
          category: 'knowledge',
          scopes: [],
          updated_at: '',
          facts: [],
          relations: [],
        }
        byName.set(name, entity)
      }
      // Each seed fact stands for one captured sentence: its memory chunk.
      const turn = `t-${record.id}`
      entity.facts.unshift({
        id: record.id,
        key,
        value,
        category: 'knowledge',
        scopes: [record.area],
        created_at,
        replaced: false,
        // The seed has no summaries or labels, like many real facts.
        summary: null,
        labels: [],
        source: {
          kind: 'turn',
          ref: `turn:${turn}`,
          session_id: `s-${turn}`,
          trust: 0.5,
        },
      })
      chunks.unshift({
        id: turn,
        session_id: `s-${turn}`,
        role: 'user',
        text: `${name}: ${key.replace(/_/g, ' ')} is ${value}.`,
        created_at,
        scopes: [record.area],
        derived: [record.id],
      })
      if (!entity.scopes.includes(record.area)) entity.scopes.push(record.area)
      if (created_at > entity.updated_at) entity.updated_at = created_at
    })

    const entities = [...byName.values()].sort((a, b) =>
      b.updated_at.localeCompare(a.updated_at),
    )
    return {
      entities,
      scopes: [...every].sort(),
      total_facts: entities.reduce((n, e) => n + e.facts.length, 0),
      total_relations: 0,
      chunks,
      total_chunks: chunks.length,
      chunks_missing: 0,
      actions: [],
      unknowns: [],
      instructions: [],
      documents: [],
      replaced_loaded: true,
      replaced_missing: 0,
    }
  },
}
