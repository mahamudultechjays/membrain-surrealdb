import type { AskLayer, LayerName } from '@/api/ask'
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

/** "Org", "Team org/team/ops", "Priya's personal": short enough for a banner. */
export function describeLayer(layer: AskLayer): string {
  if (layer.layer === 'personal') {
    return layer.owner ? `${layer.owner}'s personal` : `Personal ${layer.area}`
  }
  if (layer.layer === 'team') return `Team ${layer.area}`
  return LAYER_LABELS[layer.layer]
}

/** Recall's 0–1 match score, two decimals. */
export const formatScore = (score: number) => score.toFixed(2)
