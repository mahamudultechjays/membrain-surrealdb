import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { GraphCanvas, type GraphCanvasRef } from 'reagraph'
import type { BrainRow } from '@/components/brain/filter'
import {
  buildGraph,
  captionSpokes,
  connectionsOf,
  egoGraph,
  limitGraph,
  sizeBounds,
  typesShown,
  type Connection,
  type GraphEdge,
  type GraphNode,
} from '@/components/brain/graph/buildGraph'
import { buildCanvasTheme } from '@/components/brain/graph/canvasTheme'
import DimensionToggle from '@/components/brain/graph/DimensionToggle'
import { forcesFor, layoutFor, type Dimension } from '@/components/brain/graph/forces'
import ZoomControls from '@/components/brain/graph/ZoomControls'
import { useDocumentTheme } from '@/hooks/useDocumentTheme'

/** The overview draws at most this many nodes; focusing one shows its neighbourhood whole. */
export const OVERVIEW_LIMIT = 400
// Relation names appear once the camera is this close, relative to the fitted
// view (about two clicks of +), and go again a little further out than that,
// so they don't flicker at the edge.
const NAMES_ON_RATIO = 0.55
const NAMES_OFF_RATIO = 0.7
const NAMES_KEY = 'mb-brain-graph-names'
// How long a fit's camera glide takes before its distance is read.
const FIT_GLIDE_MS = 1100
// The +/- buttons dolly the camera by a ratio of where it stands, as membrain's do,
// so the buttons and the mouse wheel move the same way.
const ZOOM_STEP = 0.7
const ZOOM_MIN_DISTANCE = 150
const ZOOM_MAX_DISTANCE = 40000
// A drop fires the node's click right behind the drag; one this soon is the drop.
const DRAG_CLICK_GRACE = 250
const DIMENSION_KEY = 'mb-brain-graph-dimension'

const NUMBER = new Intl.NumberFormat('en-GB')

type Controls = ReturnType<GraphCanvasRef['getControls']>

function storedNames(): boolean {
  try {
    return localStorage.getItem(NAMES_KEY) === 'on'
  } catch {
    return false
  }
}

function storedDimension(): Dimension {
  try {
    return localStorage.getItem(DIMENSION_KEY) === '3d' ? '3d' : '2d'
  } catch {
    return '2d'
  }
}

interface Props {
  /** The rows the Brain filters let through. */
  rows: readonly BrainRow[]
  /** Opens a row in the list view. */
  onOpen: (rowId: string) => void
}

/**
 * Brain as a graph, on membrain's canvas: reagraph, the same force numbers,
 * the 2d/3d switch and the zoom pair in the bottom-left corner. Entities are
 * nodes, relations are edges, memory chunks hang off what they produced.
 * Clicking a node focuses it: the canvas narrows to its neighbourhood and the
 * side panel lists what memory holds about it.
 */
export default function BrainGraph({ rows, onOpen }: Props) {
  const appTheme = useDocumentTheme()
  const [dimension, setDimension] = useState<Dimension>(storedDimension)
  const [focus, setFocus] = useState<string | null>(null)
  const [depth, setDepth] = useState<1 | 2>(1)
  const canvas = useRef<GraphCanvasRef>(null)
  const frame = useRef<HTMLElement>(null)
  const draggedAt = useRef(0)
  // The node under the pointer, and where to put its card (relative to the canvas).
  // Tied to the layout run it was read in: a relayout moves nodes from under a
  // still pointer without reagraph saying so, so an older card is stale.
  const [hover, setHover] = useState<{ at: HoverAt; run: object } | null>(null)
  // Relation names: always (the toggle), or once zoomed in close enough.
  const [showNames, setShowNames] = useState(storedNames)
  const [zoomedIn, setZoomedIn] = useState(false)
  const zoomed = useRef(false)
  const watched = useRef<Controls | null>(null)
  // The camera distance of the last fitted view, which "zoomed in" is measured from.
  const fitDistance = useRef<number | null>(null)

  const full = useMemo(() => buildGraph(rows), [rows])
  // A focus the filters have since hidden falls back to the overview.
  const selected = focus ? (full.nodes.find((n) => n.id === focus) ?? null) : null
  const view = useMemo(
    () =>
      selected ? egoGraph(full, selected.id, depth) : limitGraph(full, OVERVIEW_LIMIT),
    [full, selected, depth],
  )
  // Focused, only the centre's own edges keep their names unless all are asked
  // for: the web between its neighbours would bury them. (Hover shows the rest.)
  const edges = useMemo(
    () => (selected && !showNames ? captionSpokes(view.edges, selected.id) : view.edges),
    [view.edges, selected, showNames],
  )
  const bounds = useMemo(() => sizeBounds(view.nodes), [view.nodes])
  const drawn = useMemo(() => new Map(view.nodes.map((n) => [n.id, n])), [view.nodes])
  const lines = useMemo(() => new Map(view.edges.map((e) => [e.id, e])), [view.edges])
  const legend = useMemo(() => typesShown(view.nodes).slice(0, 8), [view.nodes])
  const entities = full.nodes.filter((n) => n.data.kind !== 'chunk').length

  const changeDimension = (next: Dimension) => {
    setDimension(next)
    try {
      localStorage.setItem(DIMENSION_KEY, next)
    } catch {
      // Blocked storage: the switch still works for this visit.
    }
  }

  const zoomBy = useCallback((factor: number) => {
    const controls = canvas.current?.getControls()
    const distance = controls?.distance
    if (!controls || typeof distance !== 'number' || !Number.isFinite(distance)) return
    const next = Math.min(
      Math.max(distance * factor, ZOOM_MIN_DISTANCE),
      ZOOM_MAX_DISTANCE,
    )
    if (Math.abs(next - distance) >= 1) void controls.dollyTo(next, true)
  }, [])

  // Zoomed in or not, from the camera's distance against the fitted view.
  const onCamera = useCallback(() => {
    const distance = watched.current?.distance
    const base = fitDistance.current
    if (!base || typeof distance !== 'number') return
    const ratio = distance / base
    const next = zoomed.current ? ratio < NAMES_OFF_RATIO : ratio < NAMES_ON_RATIO
    if (next === zoomed.current) return
    zoomed.current = next
    setZoomedIn(next)
  }, [])

  /** Takes where the camera stands as "zoomed out": the fitted view. */
  const markFitted = useCallback(() => {
    const distance = watched.current?.distance
    if (typeof distance !== 'number' || !Number.isFinite(distance)) return
    fitDistance.current = distance
    onCamera()
  }, [onCamera])

  // The fitted distance is read once the fit's glide is over: a timer, so it
  // doesn't hang on camera-controls' "rest" event arriving.
  const fitTimer = useRef(0)
  const fit = useCallback(() => {
    void canvas.current?.fitNodesInView([], { animated: true })
    window.clearTimeout(fitTimer.current)
    fitTimer.current = window.setTimeout(markFitted, FIT_GLIDE_MS)
  }, [markFitted])

  /** Listens to the canvas's camera; a 2d/3d switch makes a new one. */
  const watchCamera = useCallback(() => {
    const controls = canvas.current?.getControls()
    if (!controls || controls === watched.current) return
    watched.current?.removeEventListener('update', onCamera)
    controls.addEventListener('update', onCamera)
    watched.current = controls
    // reagraph fitted this camera to the nodes when it mounted.
    markFitted()
  }, [onCamera, markFitted])
  useEffect(
    () => () => {
      watched.current?.removeEventListener('update', onCamera)
      window.clearTimeout(fitTimer.current)
    },
    [onCamera],
  )

  // reagraph says nothing when its force layout settles, so give each run a
  // time scaled to its size, show that it is laying out, then frame the result.
  // (membrain runs its own layout worker for this; for a few hundred nodes a
  // timed settle is enough.)
  const run = useMemo(() => ({ view, dimension }), [view, dimension])
  const [settledRun, setSettledRun] = useState<typeof run | null>(null)
  const settling = view.nodes.length > 0 && settledRun !== run
  useEffect(() => {
    if (!view.nodes.length) return
    const timer = window.setTimeout(
      () => {
        watchCamera()
        fit()
        setSettledRun(run)
      },
      Math.min(1200 + view.nodes.length * 8, 5000),
    )
    return () => window.clearTimeout(timer)
  }, [run, view.nodes.length, fit, watchCamera])

  // Esc lets go of the focus, as a click on empty canvas does.
  useEffect(() => {
    if (!selected) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFocus(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected])

  // Node names always. Relation names once zoomed in, when focused (the centre's
  // own), or on request. They are shown and hidden through the theme (their text
  // size), never through labelType: a labelType change makes reagraph re-run the
  // layout, and the nodes would slide about under a zooming camera.
  const names = showNames || zoomedIn || selected !== null
  const theme = useMemo(() => buildCanvasTheme(appTheme, names), [appTheme, names])

  const changeNames = () => {
    const next = !showNames
    setShowNames(next)
    try {
      localStorage.setItem(NAMES_KEY, next ? 'on' : 'off')
    } catch {
      // Blocked storage: the toggle still works for this visit.
    }
  }

  /** Where the pointer is, relative to the canvas, for a hover card. */
  const pointAt = (
    event: { nativeEvent?: { clientX: number; clientY: number } } | undefined,
  ) => {
    const box = frame.current?.getBoundingClientRect()
    const pointer = event?.nativeEvent
    if (!box || !pointer) return null
    return {
      x: pointer.clientX - box.left,
      y: pointer.clientY - box.top,
      width: box.width,
      height: box.height,
    }
  }

  return (
    <div className="graph" data-focused={selected ? '' : undefined}>
      <figure
        ref={frame}
        className="graph-canvas"
        onPointerLeave={() => setHover(null)}
        aria-label={`Graph of ${NUMBER.format(view.nodes.length)} nodes and ${NUMBER.format(view.edges.length)} links`}
      >
        {view.nodes.length > 0 ? (
          <GraphCanvas
            // reagraph keeps its layout across a prop change; a new key re-runs
            // it, so flat positions never carry into the 3d layout.
            key={dimension}
            ref={canvas}
            nodes={view.nodes}
            edges={edges}
            theme={theme}
            layoutType={layoutFor(dimension)}
            layoutOverrides={forcesFor(dimension) as never}
            cameraMode={dimension === '2d' ? 'pan' : 'rotate'}
            labelType="all"
            minNodeSize={bounds.min}
            maxNodeSize={bounds.max}
            edgeArrowPosition="end"
            selections={selected ? [selected.id] : []}
            animated
            draggable
            onNodeDragged={() => {
              draggedAt.current = Date.now()
              setHover(null)
            }}
            onNodeClick={(node) => {
              if (Date.now() - draggedAt.current < DRAG_CLICK_GRACE) return
              setHover(null)
              setFocus(node.id)
            }}
            // A click on empty canvas lets go of the focus: back to the whole map.
            onCanvasClick={() => {
              setHover(null)
              setFocus(null)
            }}
            onNodePointerOver={(node, event) => {
              const found = drawn.get(node.id)
              const at = pointAt(event)
              if (!found || !at) return
              setHover({
                run,
                at: {
                  ...at,
                  node: found,
                  connections: connectionsOf(full.edges, found.id),
                },
              })
            }}
            onNodePointerOut={() => setHover(null)}
            onEdgePointerOver={(edge, event) => {
              const found = lines.get(edge.id)
              const at = pointAt(event)
              if (!found || !at) return
              setHover({ run, at: { ...at, edge: found } })
            }}
            onEdgePointerOut={() => setHover(null)}
            // A relation's line opens that relation in the list.
            onEdgeClick={(edge) => {
              const relation = lines.get(edge.id)?.data.relation
              if (relation) onOpen(relation.id)
            }}
          />
        ) : (
          <p className="graph-empty">Nothing to draw: no entities match these filters.</p>
        )}

        {hover && hover.run === run && !settling && <HoverCard {...hover.at} />}

        {selected ? (
          <button
            type="button"
            className="graph-pill graph-focus"
            onClick={() => setFocus(null)}
          >
            <span>
              Focused on <strong>{selected.label}</strong> ·{' '}
              {NUMBER.format(view.nodes.length - 1)} around it
            </span>
            <span className="graph-focus-exit">Show all</span>
          </button>
        ) : (
          full.nodes.length > view.nodes.length && (
            <p className="graph-pill graph-note">
              Showing the {NUMBER.format(view.nodes.length)} best-connected of{' '}
              {NUMBER.format(full.nodes.length)} nodes. Click one to see its
              neighbourhood, or narrow with the filters.
            </p>
          )
        )}

        {settling && (
          <output className="graph-pill graph-settling">
            Laying out {NUMBER.format(view.nodes.length)} nodes…
          </output>
        )}

        <div className="graph-controls">
          <DimensionToggle dimension={dimension} onChange={changeDimension} />
          <ZoomControls
            onZoomIn={() => zoomBy(ZOOM_STEP)}
            onZoomOut={() => zoomBy(1 / ZOOM_STEP)}
            onFit={fit}
          />
          <div className="graph-pill">
            <button
              type="button"
              className="graph-pill-btn graph-names"
              aria-pressed={showNames}
              title="Always show relation names"
              onClick={changeNames}
            >
              Relation names
            </button>
          </div>
        </div>

        <div className="graph-readout">
          <ul className="graph-legend" aria-label="Entity types">
            {legend.map((t) => (
              <li key={t.type}>
                <span className="graph-swatch" style={{ background: t.fill }} />
                {t.type}
              </li>
            ))}
          </ul>
          <p>
            {NUMBER.format(entities)} entities · {NUMBER.format(full.edges.length)} links
            {!names && view.edges.length > 0 && (
              <span className="graph-hint"> · zoom in for relation names</span>
            )}
          </p>
        </div>
      </figure>

      {selected && (
        <NodePanel
          node={selected}
          incoming={connectionsOf(full.edges, selected.id).filter(
            (c) => !c.outgoing && c.edge.data.relation,
          )}
          depth={depth}
          onDepth={setDepth}
          onOpen={onOpen}
          onClose={() => setFocus(null)}
        />
      )}
    </div>
  )
}

const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
/** Agent Memory's nanosecond timestamps, to a date people read. */
function formatDate(value: string): string {
  const time = Date.parse(value.replace(/(\.\d{3})\d+/, '$1'))
  return Number.isNaN(time) ? '—' : DATE.format(time)
}
const plural = (n: number, one: string) =>
  `${NUMBER.format(n)} ${one}${n === 1 ? '' : 's'}`

/** The current facts and the relations of a node, the way both panels show them. */
function split(node: GraphNode) {
  const facts = node.data.records.filter((r) => r.kind === 'fact' && !r.replaced)
  const relations = node.data.records.filter((r) => r.kind === 'relation')
  return { facts, relations }
}

/** What the pointer is over, and where (relative to the canvas). */
interface HoverAt {
  node?: GraphNode
  /** A node's connections both ways, for its card. */
  connections?: Connection[]
  edge?: GraphEdge
  x: number
  y: number
  /** The canvas size, so the card flips to stay inside it. */
  width: number
  height: number
}

/** How many connections a node's card lists before "and N more". */
const CARD_CONNECTIONS = 5

/** One connection as a line of text: "ships_to → Reno" out, "Acme → ships_to" in. */
function ConnectionLine({ connection }: { connection: Connection }) {
  const { edge, outgoing, other } = connection
  return outgoing ? (
    <>
      <span className="mono">{edge.label}</span> → {other}
    </>
  ) : (
    <>
      {other} → <span className="mono">{edge.label}</span>
    </>
  )
}

/** A short card beside the pointer: what this node or line is, before any click. */
function HoverCard({ node, connections = [], edge, x, y, width, height }: HoverAt) {
  const card = useRef<HTMLDivElement>(null)
  // Below-right of the pointer, flipped and clamped by its real size so it never
  // runs past the canvas edge (which clips it). Set before paint: no jump.
  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const gap = 14
    const margin = 8
    const w = el.offsetWidth
    const h = el.offsetHeight
    let left = x + gap
    if (left + w > width - margin) left = x - gap - w
    let top = y + gap
    if (top + h > height - margin) top = y - gap - h
    el.style.left = `${Math.max(margin, Math.min(left, width - margin - w))}px`
    el.style.top = `${Math.max(margin, Math.min(top, height - margin - h))}px`
  })
  if (edge) {
    const relation = edge.data.relation
    return (
      <div ref={card} className="graph-hover" aria-hidden="true">
        <p className="graph-hover-name">
          {edge.data.from} <span className="graph-hover-arrow">→</span> {edge.data.to}
        </p>
        <p className="graph-hover-relation mono">{edge.label || 'about'}</p>
        {relation?.summary && <p className="graph-hover-text">{relation.summary}</p>}
        {relation && (
          <p className="graph-hover-meta">
            {relation.category && `${relation.category} · `}
            {formatDate(relation.created_at)}
          </p>
        )}
        {!relation && (
          <p className="graph-hover-meta">
            Facts about {edge.data.to} were extracted from this text.
          </p>
        )}
        {relation && <p className="graph-hover-hint">Click to open in the list</p>}
      </div>
    )
  }
  if (!node) return null
  const { data } = node
  const { facts } = split(node)
  const summary = facts.find((f) => f.summary)?.summary
  return (
    <div ref={card} className="graph-hover" aria-hidden="true">
      <p className="graph-hover-name">
        <span className="graph-swatch" style={{ background: node.fill }} />
        {data.kind === 'chunk' ? 'Memory chunk' : data.name}
      </p>
      <p className="graph-hover-meta">
        {data.type}
        {data.kind === 'entity' && ` · ${plural(facts.length, 'fact')}`}
        {` · ${plural(connections.length, 'link')}`}
        {data.kind === 'ghost' && ' · only named by relations'}
      </p>
      {data.chunk && (
        <p className="graph-hover-text">
          {data.chunk.text.replace(/\s+/g, ' ').slice(0, 220)}
        </p>
      )}
      {summary && <p className="graph-hover-text">{summary}</p>}
      {facts.length > 0 && (
        <ul>
          {facts.slice(0, 3).map((f) => (
            <li key={f.id}>
              <span className="mono">{f.key}</span> = {f.value}
            </li>
          ))}
        </ul>
      )}
      {connections.length > 0 && data.kind !== 'chunk' && (
        <>
          <p className="graph-hover-heading">Connections</p>
          <ul>
            {connections.slice(0, CARD_CONNECTIONS).map((c) => (
              <li key={c.edge.id}>
                <ConnectionLine connection={c} />
              </li>
            ))}
            {connections.length > CARD_CONNECTIONS && (
              <li className="graph-hover-meta">
                and {NUMBER.format(connections.length - CARD_CONNECTIONS)} more
              </li>
            )}
          </ul>
        </>
      )}
      {data.updated && (
        <p className="graph-hover-meta">Updated {formatDate(data.updated)}</p>
      )}
      <p className="graph-hover-hint">Click to focus</p>
    </div>
  )
}

/** Everything memory holds about the focused node, each row openable in the list. */
function NodePanel({
  node,
  incoming,
  depth,
  onDepth,
  onOpen,
  onClose,
}: {
  node: GraphNode
  /** Relations other entities hold that point at this one. */
  incoming: Connection[]
  depth: 1 | 2
  onDepth: (depth: 1 | 2) => void
  onOpen: (rowId: string) => void
  onClose: () => void
}) {
  const { data } = node
  const { facts, relations } = split(node)
  const replaced = data.records.filter((r) => r.kind === 'fact' && r.replaced).length
  const categories = [...new Set(data.records.map((r) => r.category).filter(Boolean))]
  const chunk = data.chunk
  return (
    <aside className="graph-side" aria-label={`About ${data.name}`}>
      <div className="graph-side-head">
        <div>
          <h2>{chunk ? 'Memory chunk' : data.name}</h2>
          <p>
            <span className="graph-swatch" style={{ background: node.fill }} />
            {data.type} · {plural(data.degree, 'link')}
          </p>
        </div>
        <button
          type="button"
          className="graph-close"
          aria-label="Close"
          title="Close (Esc)"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <fieldset className="graph-pill graph-depth">
        <legend className="visually-hidden">Neighbourhood depth</legend>
        {([1, 2] as const).map((d) => (
          <button
            key={d}
            type="button"
            className="graph-pill-btn"
            aria-pressed={depth === d}
            onClick={() => onDepth(d)}
          >
            {d} hop{d === 1 ? '' : 's'}
          </button>
        ))}
      </fieldset>

      {chunk && (
        <>
          <p className="graph-chunk-text">{chunk.text}</p>
          <button type="button" className="brain-link" onClick={() => onOpen(chunk.id)}>
            Open in the list
          </button>
        </>
      )}
      {data.kind === 'ghost' && (
        <p className="brain-muted">
          Nothing about {data.name} is in view itself; it is drawn because relations point
          to it.
        </p>
      )}

      <dl className="graph-facts">
        <dt>Name</dt>
        <dd>{chunk ? '—' : data.name}</dd>
        <dt>Type</dt>
        <dd>{data.type || '—'}</dd>
        {data.ref && (
          <>
            <dt>Ref</dt>
            <dd className="mono">{data.ref}</dd>
          </>
        )}
        {chunk && (
          <>
            <dt>Role</dt>
            <dd>{chunk.role || '—'}</dd>
            <dt>Session</dt>
            <dd className="mono">{chunk.session_id}</dd>
          </>
        )}
        <dt>Space</dt>
        <dd className="mono">{data.scopes.join(', ') || '—'}</dd>
        {categories.length > 0 && (
          <>
            <dt>Category</dt>
            <dd>{categories.join(', ')}</dd>
          </>
        )}
        <dt>{chunk ? 'Saved' : 'Updated'}</dt>
        <dd>{data.updated ? formatDate(data.updated) : '—'}</dd>
        {data.kind === 'entity' && (
          <>
            <dt>Holds</dt>
            <dd>
              {plural(facts.length, 'fact')}, {plural(relations.length, 'relation')}
              {replaced > 0 && `, ${NUMBER.format(replaced)} replaced`}
            </dd>
          </>
        )}
      </dl>

      {facts.length > 0 && (
        <section>
          <h3>Facts ({NUMBER.format(facts.length)})</h3>
          <ul className="graph-rows">
            {facts.map((r) => (
              <li key={r.id}>
                <button type="button" className="brain-link" onClick={() => onOpen(r.id)}>
                  <span className="mono">{r.key}</span> = {r.value}
                </button>
                {r.summary && <p className="graph-row-summary">{r.summary}</p>}
                <p className="graph-row-meta">
                  {r.category && `${r.category} · `}
                  {formatDate(r.created_at)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {relations.length > 0 && (
        <section>
          <h3>Relations ({NUMBER.format(relations.length)})</h3>
          <ul className="graph-rows">
            {relations.map((r) => (
              <li key={r.id}>
                <button type="button" className="brain-link" onClick={() => onOpen(r.id)}>
                  <span className="mono">{r.key}</span> → {r.value}
                </button>
                {r.summary && <p className="graph-row-summary">{r.summary}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {incoming.length > 0 && (
        <section>
          <h3>Pointed to by ({NUMBER.format(incoming.length)})</h3>
          <ul className="graph-rows">
            {incoming.map((c) => {
              const relation = c.edge.data.relation
              return (
                <li key={c.edge.id}>
                  <button
                    type="button"
                    className="brain-link"
                    onClick={() => relation && onOpen(relation.id)}
                  >
                    <ConnectionLine connection={c} />
                  </button>
                  {relation?.summary && (
                    <p className="graph-row-summary">{relation.summary}</p>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </aside>
  )
}
