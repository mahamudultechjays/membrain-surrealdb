/**
 * Force numbers for the Brain graph, ported from membrain's lib/forces.js so
 * the two canvases lay out the same way.
 *
 * Split per dimension because reagraph doubles the charge for flat layouts
 * past 25 edges, and repulsion spread over three axes buys less separation as
 * seen from any one viewpoint. The link distance is sized against labels, not
 * dots: a caption is far wider than its node, so connected nodes have to sit
 * further apart than their own names are long.
 */

export type Dimension = '2d' | '3d'

export const BASE_LINK_DISTANCE: Record<Dimension, number> = { '2d': 80, '3d': 175 }
export const NODE_STRENGTH: Record<Dimension, number> = { '2d': -210, '3d': -875 }

/** A chunk's link to what it produced: provenance, drawn a little further out. */
const CHUNK_LINK_MULTIPLE = 1.4

/** What a chunk's edge reads when relation names show: the text is about that entity. */
export const CHUNK_EDGE_LABEL = 'about'

/** Chunk edges are told apart by id, not label, since labels can be blanked for display. */
export const CHUNK_EDGE_PREFIX = 'c:'

interface LinkLike {
  id?: string
}

/** The resting length of one edge, by what the edge is. */
export function linkDistanceFor(dimension: Dimension) {
  const base = BASE_LINK_DISTANCE[dimension]
  return (link: LinkLike) =>
    link?.id?.startsWith(CHUNK_EDGE_PREFIX) ? base * CHUNK_LINK_MULTIPLE : base
}

// Module constants, so a re-render never hands reagraph a new object and
// re-runs its layout.
const FORCES: Record<Dimension, { nodeStrength: number; linkDistance: unknown }> = {
  '2d': { nodeStrength: NODE_STRENGTH['2d'], linkDistance: linkDistanceFor('2d') },
  '3d': { nodeStrength: NODE_STRENGTH['3d'], linkDistance: linkDistanceFor('3d') },
}

/** The force profile the 2d/3d switch picks. */
export const forcesFor = (dimension: Dimension) => FORCES[dimension]
export const layoutFor = (dimension: Dimension) =>
  dimension === '2d' ? ('forceDirected2d' as const) : ('forceDirected3d' as const)
