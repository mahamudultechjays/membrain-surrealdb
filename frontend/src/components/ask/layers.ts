import type { AskMode, FactProvenance, LayerName } from '@/api/ask'
import type { Grant } from '@/api/auth'

export const LAYER_LABELS: Record<LayerName, string> = {
  org: 'Org',
  team: 'Team',
  personal: 'Personal',
}

/** The Search modes, as the mode picker and the answer summary name them. */
export const MODE_LABELS: Record<AskMode, string> = {
  default: 'Default',
  best_match: 'Best match',
  by_layer: 'By layer',
}

/** What each mode does when org, team and personal hold different values. */
export const MODE_HINTS: Record<AskMode, string> = {
  default: 'Lists every layer as it is. Values are not compared.',
  best_match:
    'Uses the value that best matches the question. On a near-tie, the broader layer wins: org, then team, then personal.',
  by_layer: 'Flags values that differ between layers. Nothing is chosen for you.',
}

const LAYER_RANK: Record<LayerName, number> = { org: 0, team: 1, personal: 2 }

/**
 * Every scope these grants can read, once each, org first. This is what the
 * backend will recall from, so the user sees the blast radius before asking.
 */
export function readAreas(grants: readonly Grant[]): string[] {
  const seen = new Map<string, Grant>()
  for (const grant of grants) {
    if (!seen.has(grant.scope_path)) seen.set(grant.scope_path, grant)
  }
  return [...seen.values()]
    .sort(
      (a, b) =>
        LAYER_RANK[a.layer] - LAYER_RANK[b.layer] ||
        a.scope_path.localeCompare(b.scope_path),
    )
    .map((grant) => grant.scope_path)
}

/** The user's own space: their personal scope, or null when they have none. */
export function ownScope(grants: readonly Grant[]): string | null {
  return grants.find((g) => g.layer === 'personal')?.scope_path ?? null
}

/**
 * The spaces to leave out when a page opens, so it starts on the user's own
 * space alone; nothing (so everything is in) when they have no own space.
 * Pages keep "left out" rather than "picked" so a newly granted space shows up
 * ticked once the user has chosen "all".
 */
export function startExcluded(grants: readonly Grant[]): string[] {
  const own = ownScope(grants)
  return own ? readAreas(grants).filter((path) => path !== own) : []
}

/**
 * A space as people think of it: "Org", "My space", the owner's name for
 * someone else's space, or "Team ops" for a shared one.
 */
export function spaceName(grant: Grant): string {
  if (grant.layer === 'org') return 'Org'
  if (grant.layer === 'personal') return 'My space'
  if (grant.owner) return grant.owner
  return `Team ${grant.scope_path.split('/').pop() ?? grant.scope_path}`
}

/** Recall's 0–1 match score, two decimals. */
export const formatScore = (score: number) => score.toFixed(2)

/** How a fact was written, as Agent Memory's source kinds read to people. */
export const SOURCE_KIND_LABELS: Record<string, string> = {
  upsert: 'Structured fact',
  turn: 'Taken from chat',
  consolidation: 'Consolidated from other facts',
}

/** Green for a structured fact (0.95), plain for one from chat (0.5), amber below. */
export function trustTone(trust: number): 'good' | 'warn' | undefined {
  if (trust >= 0.8) return 'good'
  if (trust < 0.5) return 'warn'
  return undefined
}

/** "Taken from chat · confidence 0.80 · added 9 Nov 2026", for a chip's title. */
export function describeProvenance(p: FactProvenance): string {
  const parts = [
    p.source_kind ? (SOURCE_KIND_LABELS[p.source_kind] ?? p.source_kind) : null,
    p.confidence != null ? `confidence ${formatScore(p.confidence)}` : null,
    p.created_at ? `added ${formatDate(p.created_at)}` : null,
  ]
  return parts.filter(Boolean).join(' · ')
}

/** "9 Nov 2026" from an ISO time; the input as is when it does not parse. */
export function formatDate(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
}
