import { darkTheme, lightTheme, type Theme } from 'reagraph'

/*
 * The reagraph canvas theme, built the way membrain's canvasTheme.js builds
 * it: the base light or dark theme, with the canvas, label ink and accent
 * swapped for this app's tokens. The canvas is drawn by WebGL and can't read
 * CSS custom properties, so the tokens from index.css are repeated as hex.
 */

export type AppTheme = 'light' | 'dark'

export const GRAPH_THEME: Record<
  AppTheme,
  { canvas: string; ink: string; accent: string; line: string }
> = {
  light: { canvas: '#f9fafb', ink: '#111827', accent: '#0e7a55', line: '#d1d5db' },
  dark: { canvas: '#161d1a', ink: '#e6ece9', accent: '#3fbf8f', line: '#34403b' },
}

/** A relation name's size when shown; reagraph's own default. */
const RELATION_NAME_SIZE = 6
/**
 * A relation name's size when hidden: too small to draw. Names are hidden by
 * size, not by reagraph's labelType, because changing labelType re-runs the
 * whole layout and the nodes slide about; a theme change only repaints.
 */
const HIDDEN_NAME_SIZE = 0.01

export function buildCanvasTheme(appTheme: AppTheme, relationNames = true): Theme {
  const pal = GRAPH_THEME[appTheme]
  const base = appTheme === 'light' ? lightTheme : darkTheme
  return {
    ...base,
    canvas: { ...base.canvas, background: pal.canvas },
    node: {
      ...base.node,
      activeFill: pal.accent,
      // Selecting a node must not fade the rest: focus mode already narrows the
      // canvas to its neighbourhood, so every node drawn stays at full strength.
      inactiveOpacity: 1,
      // Labels in full-contrast ink, outlined in the canvas colour so they stay
      // readable where they cross an edge or another node.
      label: {
        ...base.node.label,
        color: pal.ink,
        activeColor: pal.accent,
        stroke: pal.canvas,
      },
      subLabel: base.node.subLabel && {
        ...base.node.subLabel,
        color: pal.ink,
        activeColor: pal.accent,
        stroke: pal.canvas,
      },
    },
    edge: {
      ...base.edge,
      fill: pal.line,
      activeFill: pal.accent,
      inactiveOpacity: 0.9,
      label: {
        ...base.edge.label,
        color: pal.ink,
        activeColor: pal.accent,
        // Outlined like node names, so a name stays legible across the lines.
        stroke: pal.canvas,
        fontSize: relationNames ? RELATION_NAME_SIZE : HIDDEN_NAME_SIZE,
      },
    },
    arrow: { ...base.arrow, fill: pal.line, activeFill: pal.accent },
  }
}

/**
 * Node colours by entity type: membrain's TYPE_COLORS, keyed by the lower-case
 * types Agent Memory extracts, with the types it has that membrain doesn't
 * given the free hues. Chunks are muted stone, as membrain draws its
 * provenance layer: the background the knowledge stands on.
 */
export const TYPE_COLORS: Record<string, string> = {
  person: '#ec4899',
  project: '#8b5cf6',
  product: '#3b82f6',
  concept: '#64748b',
  organisation: '#10b981',
  organization: '#10b981',
  vendor: '#10b981',
  metric: '#22d3ee',
  channel: '#f59e0b',
  task: '#eab308',
  decision: '#ef4444',
  belief: '#f97316',
  preference: '#f43f5e',
  location: '#14b8a6',
  event: '#84cc16',
  other: '#94a3b8',
}
export const CHUNK_COLOR = '#a8a29e'
const DEFAULT_COLOR = '#94a3b8'

export const colorFor = (type: string) => TYPE_COLORS[type] ?? DEFAULT_COLOR
