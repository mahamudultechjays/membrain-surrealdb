import { act, fireEvent, render, screen, within } from '@testing-library/react'
import type { BrainEntity } from '@/api/brain'
import { toRows } from '@/components/brain/filter'
import BrainGraph from '@/components/brain/graph/BrainGraph'

// reagraph draws with WebGL, which jsdom lacks: stand in a canvas that lists
// its nodes as buttons and says which layout it was given.
vi.mock('reagraph', () => {
  const base = {
    canvas: {},
    node: { label: {}, subLabel: {} },
    edge: { label: {} },
    arrow: {},
  }
  return {
    lightTheme: base,
    darkTheme: base,
    GraphCanvas: (props: {
      nodes: { id: string; label: string }[]
      edges: { id: string; label: string }[]
      layoutType: string
      labelType: string
      selections: string[]
      theme: {
        node: { inactiveOpacity?: number }
        edge: { label: { fontSize?: number } }
      }
      onNodeClick: (node: { id: string }) => void
      onCanvasClick: () => void
      onNodePointerOver: (
        node: { id: string },
        event: { nativeEvent: { clientX: number; clientY: number } },
      ) => void
      onNodePointerOut: () => void
      onEdgePointerOver: (
        edge: { id: string },
        event: { nativeEvent: { clientX: number; clientY: number } },
      ) => void
      onEdgePointerOut: () => void
      onEdgeClick: (edge: { id: string }) => void
    }) => (
      <div
        data-testid="canvas"
        data-layout={props.layoutType}
        data-labels={props.labelType}
        data-relation-size={props.theme.edge.label.fontSize}
      >
        {props.edges.map((e) => (
          <button
            key={e.id}
            type="button"
            onClick={() => props.onEdgeClick({ id: e.id })}
            onMouseEnter={() =>
              props.onEdgePointerOver(
                { id: e.id },
                { nativeEvent: { clientX: 60, clientY: 50 } },
              )
            }
            onMouseLeave={() => props.onEdgePointerOut()}
          >
            edge {e.id} [{e.label}]
          </button>
        ))}
        {props.nodes.map((n) => (
          <button
            key={n.id}
            type="button"
            aria-pressed={props.selections.includes(n.id)}
            // Faded by reagraph when something is selected and this isn't active.
            data-dim={
              props.selections.length > 0 &&
              !props.selections.includes(n.id) &&
              (props.theme.node.inactiveOpacity ?? 0.2) < 1
            }
            onClick={() => props.onNodeClick({ id: n.id })}
            onMouseEnter={() =>
              props.onNodePointerOver(
                { id: n.id },
                { nativeEvent: { clientX: 40, clientY: 30 } },
              )
            }
            onMouseLeave={() => props.onNodePointerOut()}
          >
            node {n.label}
          </button>
        ))}
        <button type="button" onClick={() => props.onCanvasClick()}>
          empty canvas
        </button>
        <span>{props.edges.length} edges drawn</span>
      </div>
    ),
  }
})

const AT = '2026-11-03T10:00:00+00:00'
const ENTITIES: BrainEntity[] = [
  {
    ref: 'organisation/acme',
    name: 'Acme Logistics',
    entity_type: 'organisation',
    category: 'knowledge',
    scopes: ['org/x'],
    updated_at: AT,
    facts: [
      {
        id: 'f1',
        key: 'lead_time',
        value: '18 days',
        category: 'context',
        scopes: ['org/x'],
        created_at: AT,
        replaced: false,
        summary: 'Acme takes 18 days to deliver',
        labels: [],
      },
    ],
    relations: [
      {
        id: 'r1',
        label: 'ships_to',
        object_ref: 'location/reno',
        object_name: 'Reno warehouse',
        category: 'context',
        scopes: ['org/x'],
        created_at: AT,
        summary: null,
        labels: [],
      },
    ],
  },
]
const ROWS = toRows(ENTITIES)

describe('BrainGraph', () => {
  afterEach(() => localStorage.clear())

  it('draws entities flat by default, and the 2d/3d switch re-lays them out and is remembered', () => {
    render(<BrainGraph rows={ROWS} onOpen={vi.fn<(id: string) => void>()} />)

    const canvas = screen.getByTestId('canvas')
    expect(canvas).toHaveAttribute('data-layout', 'forceDirected2d')
    expect(
      within(canvas).getByRole('button', { name: 'node Acme Logistics' }),
    ).toBeVisible()
    expect(
      within(canvas).getByRole('button', { name: 'node Reno warehouse' }),
    ).toBeVisible()
    expect(screen.getByText('1 edges drawn')).toBeInTheDocument()
    expect(screen.getByText('2 entities · 1 links')).toBeInTheDocument()

    const dims = screen.getByRole('group', { name: 'Graph dimension' })
    expect(within(dims).getByRole('button', { name: '2d' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    fireEvent.click(within(dims).getByRole('button', { name: '3d' }))
    expect(screen.getByTestId('canvas')).toHaveAttribute('data-layout', 'forceDirected3d')
    expect(localStorage.getItem('mb-brain-graph-dimension')).toBe('3d')
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument()
  })

  it('focuses a clicked node, lists what memory holds about it, and opens a row in the list', () => {
    const onOpen = vi.fn<(id: string) => void>()
    render(<BrainGraph rows={ROWS} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: 'node Acme Logistics' }))
    expect(screen.getByRole('button', { name: 'node Acme Logistics' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    const panel = screen.getByRole('complementary', { name: 'About Acme Logistics' })
    expect(within(panel).getByText('Facts (1)')).toBeInTheDocument()
    expect(within(panel).getByText('Relations (1)')).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: 'lead_time = 18 days' }))
    expect(onOpen).toHaveBeenCalledWith('fact:f1')

    // Reno is only a relation's target here: said so, not left blank.
    fireEvent.click(screen.getByRole('button', { name: 'node Reno warehouse' }))
    expect(
      within(screen.getByRole('complementary')).getByText(
        /drawn because relations point to it/,
      ),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Show all/ }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('keeps the whole neighbourhood at full strength, and a click on empty canvas lets go', () => {
    render(<BrainGraph rows={ROWS} onOpen={vi.fn<(id: string) => void>()} />)

    fireEvent.click(screen.getByRole('button', { name: 'node Acme Logistics' }))
    expect(screen.getByRole('button', { name: 'node Reno warehouse' })).toHaveAttribute(
      'data-dim',
      'false',
    )

    fireEvent.click(screen.getByRole('button', { name: 'empty canvas' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'node Acme Logistics' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('shows a node’s card on hover, and its whole record when focused', () => {
    vi.useFakeTimers()
    render(<BrainGraph rows={ROWS} onOpen={vi.fn<(id: string) => void>()} />)
    // No card while the layout is still moving nodes about.
    act(() => vi.advanceTimersByTime(5000))
    vi.useRealTimers()
    const acme = screen.getByRole('button', { name: 'node Acme Logistics' })

    fireEvent.mouseEnter(acme)
    const card = document.querySelector('.graph-hover') as HTMLElement
    expect(card).toHaveTextContent('Acme Logistics')
    expect(card).toHaveTextContent('organisation · 1 fact · 1 link')
    expect(card).toHaveTextContent('Acme takes 18 days to deliver')
    expect(card).toHaveTextContent('lead_time = 18 days')
    expect(card).toHaveTextContent('Connections')
    expect(card).toHaveTextContent('ships_to → Reno warehouse')
    fireEvent.mouseLeave(acme)
    expect(document.querySelector('.graph-hover')).toBeNull()

    // The far end lists the relation coming in.
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'node Reno warehouse' }))
    expect(document.querySelector('.graph-hover')).toHaveTextContent(
      'Acme Logistics → ships_to',
    )
    fireEvent.mouseLeave(screen.getByRole('button', { name: 'node Reno warehouse' }))

    fireEvent.click(acme)
    const panel = screen.getByRole('complementary', { name: 'About Acme Logistics' })
    const field = (name: string) =>
      within(panel).getByText(name, { selector: 'dt' }).nextElementSibling?.textContent
    expect(field('Name')).toBe('Acme Logistics')
    expect(field('Type')).toBe('organisation')
    expect(field('Ref')).toBe('organisation/acme')
    expect(field('Space')).toBe('org/x')
    expect(field('Holds')).toBe('1 fact, 1 relation')
    expect(within(panel).getByText('Acme takes 18 days to deliver')).toBeInTheDocument()
  })

  it('keeps relation names off until asked for, and names only a focused node’s own lines', () => {
    render(<BrainGraph rows={ROWS} onOpen={vi.fn<(id: string) => void>()} />)
    const canvas = () => screen.getByTestId('canvas')

    // reagraph's labelType never changes (a change re-runs its layout): names
    // come and go through the theme's text size instead.
    expect(canvas()).toHaveAttribute('data-labels', 'all')
    const named = () => Number(canvas().getAttribute('data-relation-size')) > 1

    // Overview: node names only, with a hint where the counts are.
    expect(named()).toBe(false)
    expect(screen.getByText(/zoom in for relation names/)).toBeInTheDocument()

    // The toggle names every line, and is remembered.
    fireEvent.click(screen.getByRole('button', { name: 'Relation names' }))
    expect(named()).toBe(true)
    expect(localStorage.getItem('mb-brain-graph-names')).toBe('on')
    expect(screen.queryByText(/zoom in for relation names/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Relation names' }))
    expect(named()).toBe(false)

    // Focused: names on, but only on lines touching the focused node.
    fireEvent.click(screen.getByRole('button', { name: 'node Reno warehouse' }))
    expect(named()).toBe(true)
    expect(screen.getByRole('button', { name: /^edge relation:r1/ })).toHaveTextContent(
      '[ships_to]',
    )
    // Esc lets go of the focus.
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('shows a line’s relation on hover, and opens it in the list on click', () => {
    vi.useFakeTimers()
    const onOpen = vi.fn<(id: string) => void>()
    render(<BrainGraph rows={ROWS} onOpen={onOpen} />)
    act(() => vi.advanceTimersByTime(5000))
    vi.useRealTimers()
    const line = screen.getByRole('button', { name: /^edge relation:r1/ })

    fireEvent.mouseEnter(line)
    const card = document.querySelector('.graph-hover') as HTMLElement
    expect(card).toHaveTextContent('Acme Logistics → Reno warehouse')
    expect(card).toHaveTextContent('ships_to')
    expect(card).toHaveTextContent('Click to open in the list')

    fireEvent.click(line)
    expect(onOpen).toHaveBeenCalledWith('relation:r1')
  })

  it('says when the filters leave nothing to draw', () => {
    render(<BrainGraph rows={[]} onOpen={vi.fn<(id: string) => void>()} />)
    expect(screen.getByText(/no entities match these filters/)).toBeInTheDocument()
  })
})
