import type { LayerName } from '@/api/ask'
import type { Grant } from '@/api/auth'

export const LAYER_LABELS: Record<LayerName, string> = {
  org: 'Org',
  team: 'Team',
  personal: 'Personal',
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
