import type { Dimension } from '@/components/brain/graph/forces'

/**
 * The 2d/3d switch: membrain's components/graph/DimensionToggle.jsx, in this
 * app's styles. The force profiles it picks between live in ./forces.
 */
export default function DimensionToggle({
  dimension,
  onChange,
}: {
  dimension: Dimension
  onChange: (dimension: Dimension) => void
}) {
  return (
    <fieldset className="graph-pill">
      <legend className="visually-hidden">Graph dimension</legend>
      {(['2d', '3d'] as const).map((dim) => (
        <button
          key={dim}
          type="button"
          aria-pressed={dimension === dim}
          className="graph-pill-btn graph-dim"
          onClick={() => onChange(dim)}
        >
          {dim}
        </button>
      ))}
    </fieldset>
  )
}
