import type { CapturePreviewResponse, ExtractedFact, StoreMode } from '@/api/capture'

/** Fact id -> the entity the user picked for a fact with no entity link. */
export type EntityChoices = Readonly<Record<string, string>>

/**
 * A fact can be ticked if it has a triple, if the user picked an entity for it,
 * or if full mode will re-extract it anyway.
 */
export function canKeep(
  fact: ExtractedFact,
  mode: StoreMode,
  choices: EntityChoices = {},
): boolean {
  return (
    fact.storable || mode === 'full' || (fact.needs_entity && Boolean(choices[fact.id]))
  )
}

/** The ids to send: in triples mode only facts that can become a triple. */
export function keptIds(
  preview: CapturePreviewResponse,
  mode: StoreMode,
  kept: ReadonlySet<string>,
  choices: EntityChoices = {},
): string[] {
  return preview.extracted
    .filter((fact) => kept.has(fact.id) && canKeep(fact, mode, choices))
    .map((fact) => fact.id)
}

/** The entity choices to send: only for kept facts, and only in triples mode. */
export function choicesToSend(
  preview: CapturePreviewResponse,
  mode: StoreMode,
  kept: ReadonlySet<string>,
  choices: EntityChoices,
): Record<string, string> {
  if (mode === 'full') return {}
  const out: Record<string, string> = {}
  for (const fact of preview.extracted) {
    const entity = choices[fact.id]
    if (fact.needs_entity && kept.has(fact.id) && entity) out[fact.id] = entity
  }
  return out
}

/** The fact as it will be stored: "?" replaced by the picked entity. */
export function factWithEntity(fact: ExtractedFact, choices: EntityChoices): string {
  const entity = choices[fact.id]
  return entity && fact.fact.startsWith('? · ')
    ? entity + ' · ' + fact.fact.slice(4)
    : fact.fact
}
