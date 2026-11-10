import type { ReactNode } from 'react'
import type { AskMode, LayerName } from '@/api/ask'

/*
 * The layer stack: three bars, broadest at the top. Org reads everything the
 * company agreed, team narrows it, personal is one person's own notes. The same
 * drawing marks a layer on its card and shows what each Search mode does with
 * the three of them.
 */

const BARS: { layer: LayerName; y: number; x2: number }[] = [
  { layer: 'org', y: 3.5, x2: 14 },
  { layer: 'team', y: 8, x2: 11 },
  { layer: 'personal', y: 12.5, x2: 8 },
]

const FAINT = 0.32

function Stack({
  opacity,
  children,
}: {
  opacity: (layer: LayerName) => number
  children?: ReactNode
}) {
  return (
    <svg
      className="layer-glyph"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      aria-hidden="true"
    >
      {BARS.map((bar) => (
        <line
          key={bar.layer}
          x1="2"
          x2={bar.x2}
          y1={bar.y}
          y2={bar.y}
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          opacity={opacity(bar.layer)}
        />
      ))}
      {children}
    </svg>
  )
}

/** Marks which layer a card belongs to: its own bar solid, the others faint. */
export function LayerMark({ layer }: { layer: LayerName }) {
  return <Stack opacity={(l) => (l === layer ? 1 : FAINT)} />
}

/**
 * What a mode does with the layers. Default lists all three as they are, Best
 * match keeps one value (a dot on the chosen bar), By layer flags the bars
 * that disagree.
 */
export function ModeGlyph({ mode }: { mode: AskMode }) {
  if (mode === 'best_match') {
    return (
      <Stack opacity={(l) => (l === 'team' ? 1 : FAINT)}>
        <circle className="layer-glyph-pick" cx="14" cy="8" r="1.9" fill="currentColor" />
      </Stack>
    )
  }
  if (mode === 'by_layer') {
    return (
      <Stack opacity={() => 0.85}>
        <circle className="layer-glyph-flag" cx="14" cy="8" r="1.9" fill="currentColor" />
        <circle
          className="layer-glyph-flag"
          cx="11"
          cy="12.5"
          r="1.9"
          fill="currentColor"
        />
      </Stack>
    )
  }
  return <Stack opacity={() => 0.85} />
}
