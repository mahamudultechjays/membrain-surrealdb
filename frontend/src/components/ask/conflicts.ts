import type { AskLayer } from '@/api/ask'
import { describeLayer } from '@/components/ask/layers'

export interface ConflictValue {
  value: string
  /** Layers that hold this value, in the order the answer lists them. */
  layers: string[]
}

export interface Conflict {
  /** The text before " = ", e.g. "returns policy · window_days". */
  entity: string
  values: ConflictValue[]
}

const SEPARATOR = ' = '

/**
 * Facts shaped "entity · attribute = value" that disagree across layers, e.g.
 * org says window_days = 30 and Priya's notes say 60. Agent Memory does not
 * reconcile layers, so the UI only points the disagreement out; it never picks
 * a winner. Free-text facts without " = " are ignored.
 */
export function findConflicts(layers: readonly AskLayer[]): Conflict[] {
  const byEntity = new Map<string, { entity: string; values: Map<string, Set<string>> }>()

  for (const layer of layers) {
    const label = describeLayer(layer)
    for (const { fact } of layer.facts) {
      const at = fact.indexOf(SEPARATOR)
      if (at <= 0) continue
      const entity = fact.slice(0, at).trim()
      const value = fact.slice(at + SEPARATOR.length).trim()
      const key = entity.toLowerCase()
      const entry = byEntity.get(key) ?? { entity, values: new Map() }
      byEntity.set(key, entry)
      const holders = entry.values.get(value) ?? new Set<string>()
      entry.values.set(value, holders.add(label))
    }
  }

  const conflicts: Conflict[] = []
  for (const { entity, values } of byEntity.values()) {
    if (values.size < 2) continue
    // Two values inside one layer is that layer's own history, not a cross-layer clash.
    const layersInvolved = new Set([...values.values()].flatMap((s) => [...s]))
    if (layersInvolved.size < 2) continue
    conflicts.push({
      entity,
      values: [...values].map(([value, holders]) => ({ value, layers: [...holders] })),
    })
  }
  return conflicts
}
