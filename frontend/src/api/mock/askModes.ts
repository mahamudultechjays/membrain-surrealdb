import type { AskConflict, AskLayer, AskMode, ConflictValue, LayerName } from '@/api/ask'

/*
 * The mock's copy of the backend's conflict rules (app/services/ask_modes), so
 * Best match and By layer have something to show without a backend. Keep the
 * two in step: the backend is the source of truth.
 */

const LAYER_ORDER: Record<LayerName, number> = { org: 0, team: 1, personal: 2 }
const LAYER_LABELS: Record<LayerName, string> = {
  org: 'Org',
  team: 'Team',
  personal: 'Personal',
}
const SYNONYMS: Record<string, string> = {
  max: 'maximum',
  min: 'minimum',
  qty: 'quantity',
}
const STOPWORDS = new Set(['the', 'of', 'a', 'an', 'for', 'per'])
/** Live Agent Memory attribute text: "Cobalt Ridge's returns window is 60 days". */
const LIVE_SHAPE = /^(.+?)'s (.+?) is (.+)$/s
/** The mock's older shape: "returns policy · window_days = 30". */
const MOCK_SHAPE = /^(.+?) · (.+?) = (.+)$/s

interface Point {
  hitId: string
  layer: LayerName
  area: string
  score: number
  entity: string
  entityTokens: Set<string>
  keyText: string
  keyTokens: Set<string>
  value: string
  valueNorm: string
}

export interface FactVerdict {
  status: 'used' | 'set_aside'
  reason: string
}

export interface ModeResult {
  conflicts: AskConflict[]
  /** Hit id -> conflict id, for every fact in a conflict. */
  conflictOf: Map<string, string>
  /** Hit id -> verdict; Best match only. */
  verdicts: Map<string, FactVerdict>
}

export function parseFact(
  kind: string,
  text: string,
): { entity: string; key: string; value: string } | null {
  const mock = MOCK_SHAPE.exec(text)
  if (mock) return { entity: mock[1]!, key: mock[2]!, value: mock[3]! }
  if (kind !== 'attribute') return null
  const live = LIVE_SHAPE.exec(text)
  return live ? { entity: live[1]!, key: live[2]!, value: live[3]! } : null
}

const words = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)

export function keyTokens(key: string): Set<string> {
  const tokens = words(key)
    .map((t) => SYNONYMS[t] ?? t)
    .map((t) =>
      t.length > 3 && t.endsWith('s') && !t.endsWith('ss') ? t.slice(0, -1) : t,
    )
    .filter((t) => !STOPWORDS.has(t))
  return new Set(tokens)
}

const normValue = (value: string) =>
  value
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.,;:!?]+$/, '')

const sameSet = (a: Set<string>, b: Set<string>) =>
  a.size === b.size && [...a].every((x) => b.has(x))
const subset = (a: Set<string>, b: Set<string>) => [...a].every((x) => b.has(x))

function samePoint(a: Point, b: Point): boolean {
  const entity =
    a.entity === b.entity ||
    subset(a.entityTokens, b.entityTokens) ||
    subset(b.entityTokens, a.entityTokens)
  return entity && sameSet(a.keyTokens, b.keyTokens)
}

/** Facts about the same entity and key that disagree across two or more scopes. */
export function findConflicts(layers: readonly AskLayer[], minScore = 0): Point[][] {
  const points: Point[] = []
  for (const layer of layers)
    for (const fact of layer.facts) {
      const parsed = parseFact(fact.source.hit_kind, fact.source.text)
      if (!parsed) continue
      const entityWords = words(parsed.entity)
      points.push({
        hitId: fact.source.hit_id,
        layer: layer.layer,
        area: layer.area,
        score: fact.source.score,
        entity: entityWords.join(' '),
        entityTokens: new Set(entityWords),
        keyText: parsed.key,
        keyTokens: keyTokens(parsed.key),
        value: parsed.value.trim(),
        valueNorm: normValue(parsed.value),
      })
    }

  // Union-find over "same point" pairs.
  const parent = points.map((_, i) => i)
  const find = (i: number): number =>
    parent[i] === i ? i : (parent[i] = find(parent[i]!))
  for (let i = 0; i < points.length; i++)
    for (let j = i + 1; j < points.length; j++)
      if (samePoint(points[i]!, points[j]!)) parent[find(i)] = find(j)

  const groups = new Map<number, Point[]>()
  points.forEach((p, i) => {
    const root = find(i)
    groups.set(root, [...(groups.get(root) ?? []), p])
  })
  return [...groups.values()]
    .filter(
      (g) =>
        new Set(g.map((p) => p.valueNorm)).size >= 2 &&
        new Set(g.map((p) => p.area)).size >= 2 &&
        Math.max(...g.map((p) => p.score)) >= minScore,
    )
    .sort(
      (a, b) => Math.max(...b.map((p) => p.score)) - Math.max(...a.map((p) => p.score)),
    )
}

function conflictValues(group: Point[]): ConflictValue[] {
  const byValue = new Map<string, Point[]>()
  for (const p of group)
    byValue.set(p.valueNorm, [...(byValue.get(p.valueNorm) ?? []), p])
  return [...byValue.values()]
    .map((ps) => ({
      value: ps[0]!.value,
      layers: [...new Set(ps.map((p) => p.layer))].sort(
        (a, b) => LAYER_ORDER[a] - LAYER_ORDER[b],
      ),
      areas: [...new Set(ps.map((p) => p.area))],
      hit_ids: ps.map((p) => p.hitId),
      best_score: Math.max(...ps.map((p) => p.score)),
    }))
    .sort((a, b) => b.best_score - a.best_score)
}

/** The mode's view of an answer: conflicts for best_match and by_layer, verdicts for best_match. */
export function applyMode(
  mode: AskMode,
  layers: readonly AskLayer[],
  tieMargin: number,
  minScore = 0,
): ModeResult {
  const result: ModeResult = { conflicts: [], conflictOf: new Map(), verdicts: new Map() }
  if (mode === 'default') return result

  findConflicts(layers, minScore).forEach((group, index) => {
    const id = `c${index + 1}`
    const conflict: AskConflict = {
      id,
      entity: group[0]!.entity,
      key: group[0]!.keyText,
      values: conflictValues(group),
      winner_hit_id: null,
      reason: null,
    }
    for (const p of group) result.conflictOf.set(p.hitId, id)

    if (mode === 'best_match') {
      const byScore = [...group].sort((a, b) => b.score - a.score)
      const top = byScore[0]!
      const close = group.filter((p) => top.score - p.score <= tieMargin)
      const winner = [...close].sort(
        (a, b) =>
          LAYER_ORDER[a.layer] - LAYER_ORDER[b.layer] ||
          b.score - a.score ||
          a.area.localeCompare(b.area),
      )[0]!
      const rivals = close.filter((p) => p.valueNorm !== winner.valueNorm)
      const runnerUp = byScore.find((p) => p.valueNorm !== winner.valueNorm)
      conflict.winner_hit_id = winner.hitId
      conflict.reason =
        rivals.length > 0
          ? `Scores within ${tieMargin.toFixed(2)}, so the broader ${LAYER_LABELS[winner.layer]} layer wins`
          : `Closest match to the question (${winner.score.toFixed(2)} vs ${(runnerUp?.score ?? 0).toFixed(2)})`
      for (const p of group) {
        if (p.hitId === winner.hitId)
          result.verdicts.set(p.hitId, { status: 'used', reason: conflict.reason })
        else if (p.valueNorm === winner.valueNorm)
          result.verdicts.set(p.hitId, {
            status: 'used',
            reason: 'Agrees with the chosen value',
          })
        else
          result.verdicts.set(p.hitId, {
            status: 'set_aside',
            reason: `Disagrees with the chosen ${LAYER_LABELS[winner.layer]} value: ${winner.value}`,
          })
      }
    }
    result.conflicts.push(conflict)
  })
  return result
}
