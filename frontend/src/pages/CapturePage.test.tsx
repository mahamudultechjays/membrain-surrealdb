import { act, fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import type {
  CaptureApi,
  CapturePreviewResponse,
  CaptureStoreResponse,
  DocumentStatus,
} from '@/api/capture'
import type { Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import { setMockLatencyScale } from '@/api/mock/backend'
import { mockCaptureApi } from '@/api/mock/capture'
import CapturePage from '@/pages/CapturePage'

const PRIYA = 'org/user/u-0001'

/** Priya as the mock signs her in, plus a team scope she can write, so the picker has a choice. */
const ME: Me = {
  email: 'priya@example.com',
  name: 'Priya',
  is_admin: false,
  grants: [
    { scope_path: 'org', access: 'read', layer: 'org' },
    { scope_path: 'org/team/ops', access: 'write', layer: 'team' },
    { scope_path: PRIYA, access: 'write', layer: 'personal' },
  ],
}

beforeAll(() => setMockLatencyScale(0))
afterAll(() => setMockLatencyScale(1))
afterEach(() => vi.useRealTimers())

const PREVIEW: CapturePreviewResponse = {
  preview_id: 'prev_1',
  scope: PRIYA,
  extracted: [
    {
      id: 'e1',
      fact: 'acme logistics · ships_to = reno',
      type: 'knowledge',
      source: 'text',
      note: null,
      storable: true,
      needs_entity: false,
    },
  ],
  stats: { total: 1, uncertain: 0, corrections: 0 },
  truncated: false,
  truncated_reason: null,
  doc_id: null,
  corrections: [],
  entities: [{ name: 'acme logistics', entity_type: 'organisation' }],
  trace_id: 't-preview',
}

const STORED: CaptureStoreResponse = {
  stored_id: 'store_1',
  written: 1,
  created_facts: [],
  history: [],
  trace_id: 't-store',
}

/** A fake whose methods default to the canned answers above. */
function fakeApi(overrides: Partial<CaptureApi> = {}): CaptureApi {
  return {
    preview: vi.fn<CaptureApi['preview']>(async () => PREVIEW),
    store: vi.fn<CaptureApi['store']>(async () => STORED),
    documentStatus: vi.fn<CaptureApi['documentStatus']>(async () => {
      throw new Error('not a document')
    }),
    ...overrides,
  }
}

async function renderPage(api: CaptureApi = mockCaptureApi) {
  render(<CapturePage me={ME} api={api} />)
  // Writes go to the personal scope until another writable one is picked.
  expect(
    await screen.findByRole('button', { name: 'Capture to: My space' }),
  ).toBeInTheDocument()
}

const previewButton = () => screen.getByRole('button', { name: 'Preview' })
const keepBox = (fact: string) => screen.getByRole('checkbox', { name: `Keep ${fact}` })

describe('CapturePage', () => {
  it('previews the sample text with an uncertain fact and one only full mode can store', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Use sample text' }))
    fireEvent.click(previewButton())

    const table = await screen.findByRole('table', { name: 'Extracted facts' })
    expect(within(table).getByText('uncertain')).toBeInTheDocument()
    expect(
      screen.getByText(
        (_, el) =>
          el?.className === 'capture-stats' && /1 uncertain/.test(el.textContent ?? ''),
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('lead_time: 10 → 18 days')).toBeInTheDocument()
    expect(screen.getByText(/infer=preview · ok · trace t-/)).toBeInTheDocument()

    const pronoun = keepBox('? · is = late again')
    expect(pronoun).toBeDisabled()
    expect(pronoun).not.toBeChecked()
    expect(keepBox('acme · lead_time = 18 days')).toBeChecked()

    fireEvent.click(screen.getByRole('radio', { name: /Re-extract everything/ }))
    expect(keepBox('? · is = late again')).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Store everything' })).toBeEnabled()
  })

  it('stores the kept facts and shows what was created and changed', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Use sample text' }))
    fireEvent.click(previewButton())
    await screen.findByRole('table', { name: 'Extracted facts' })

    // Untick one fact: the store button counts only what is kept.
    fireEvent.click(keepBox('dock 3 · is = closed this week'))
    fireEvent.click(screen.getByRole('button', { name: 'Store 5 facts' }))

    const created = await screen.findByRole('table', { name: 'Created facts' })
    expect(within(created).getByText('lead_time')).toBeInTheDocument()
    expect(within(created).queryByText('closed this week')).not.toBeInTheDocument()
    expect(screen.getByText(/5 writes/)).toBeInTheDocument()
    expect(screen.getByText('lead_time: 10 → 18 days')).toBeInTheDocument()
    expect(
      screen.getByText(/POST \/api\/v1\/capture\/store · infer=triples/),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Capture something else' }))
    expect(screen.getByLabelText('What do you want to remember?')).toHaveValue('')
    expect(previewButton()).toBeDisabled()
  })

  it('lets a fact with no entity be stored by picking its entity', async () => {
    const api = fakeApi({
      preview: vi.fn<CaptureApi['preview']>(async () => ({
        ...PREVIEW,
        extracted: [
          ...PREVIEW.extracted,
          {
            id: 'e2',
            fact: '? · lead_time = 18 days',
            type: 'context',
            source: 'text',
            note: 'entity not known in preview; store with mode full',
            storable: false,
            needs_entity: true,
          },
        ],
      })),
    })
    await renderPage(api)
    fireEvent.change(screen.getByLabelText('What do you want to remember?'), {
      target: { value: 'Acme lead time is 18 days and it ships to Reno.' },
    })
    fireEvent.click(previewButton())
    await screen.findByRole('table', { name: 'Extracted facts' })

    const unlinked = keepBox('? · lead_time = 18 days')
    expect(unlinked).toBeDisabled()
    expect(screen.getByText('pick entity')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Entity for ? · lead_time = 18 days'), {
      target: { value: 'acme logistics' },
    })
    expect(unlinked).toBeEnabled()
    expect(unlinked).toBeChecked()
    expect(screen.getByText('acme logistics · lead_time = 18 days')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Store 2 facts' }))
    await waitFor(() =>
      expect(api.store).toHaveBeenCalledWith(
        expect.objectContaining({
          kept: ['e1', 'e2'],
          entity_choices: { e2: 'acme logistics' },
        }),
        expect.anything(),
      ),
    )
  })

  it('says the preview expired on a 404 and can run it again', async () => {
    const api = fakeApi({
      store: vi.fn<CaptureApi['store']>(async () => {
        throw new ApiError(404, 'Preview not found or expired; run preview again.')
      }),
    })
    await renderPage(api)

    fireEvent.change(screen.getByLabelText('What do you want to remember?'), {
      target: { value: 'Acme ships to Reno.' },
    })
    fireEvent.click(previewButton())
    fireEvent.click(await screen.findByRole('button', { name: 'Store 1 fact' }))

    expect(await screen.findByText(/Preview expired/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run preview again' }))
    await screen.findByRole('button', { name: 'Store 1 fact' })
    expect(api.preview).toHaveBeenCalledTimes(2)
  })

  it('shows the backend reason for other store errors', async () => {
    const api = fakeApi({
      store: vi.fn<CaptureApi['store']>(async () => {
        throw new ApiError(403, 'This preview belongs to another scope.')
      }),
    })
    await renderPage(api)

    fireEvent.change(screen.getByLabelText('What do you want to remember?'), {
      target: { value: 'Acme ships to Reno.' },
    })
    fireEvent.click(previewButton())
    fireEvent.click(await screen.findByRole('button', { name: 'Store 1 fact' }))

    expect(
      await screen.findByText('This preview belongs to another scope.'),
    ).toBeInTheDocument()
  })

  it('clears the preview when the scope changes', async () => {
    await renderPage(fakeApi())

    fireEvent.change(screen.getByLabelText('What do you want to remember?'), {
      target: { value: 'Acme ships to Reno.' },
    })
    fireEvent.click(previewButton())
    await screen.findByRole('table', { name: 'Extracted facts' })

    fireEvent.click(screen.getByRole('button', { name: /^Capture to:/ }))
    fireEvent.click(screen.getByRole('radio', { name: /Team ops/ }))
    expect(
      screen.queryByRole('table', { name: 'Extracted facts' }),
    ).not.toBeInTheDocument()
  })

  it('disables Preview for text over the limit and points to the Document tab', async () => {
    await renderPage(fakeApi())

    fireEvent.change(screen.getByLabelText('What do you want to remember?'), {
      target: { value: 'a'.repeat(20_001) },
    })

    expect(previewButton()).toBeDisabled()
    expect(screen.getByText(/1 characters over the limit/)).toHaveTextContent(
      'Use the Document tab',
    )
  })

  it('uploads a document as base64 and polls its status until ready', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const statuses: DocumentStatus[] = [
      status(
        'processing',
        false,
        'Agent Memory is chunking and indexing the document...',
      ),
      status('ready', true, 'Processed: passages are searchable.'),
    ]
    const api = fakeApi({
      preview: vi.fn<CaptureApi['preview']>(async () => ({
        ...PREVIEW,
        doc_id: 'doc_1',
      })),
      documentStatus: vi.fn<CaptureApi['documentStatus']>(
        async () => statuses.shift() ?? status('ready', true, ''),
      ),
    })
    await renderPage(api)

    fireEvent.click(screen.getByRole('tab', { name: 'Document' }))
    expect(screen.getByText(/no dry run for files/)).toBeInTheDocument()
    const file = new File(['Acme ships to Reno.'], 'notes.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByLabelText(/^File/), { target: { files: [file] } })
    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    fireEvent.click(previewButton())

    expect(await screen.findByText('processing')).toBeInTheDocument()
    expect(api.preview).toHaveBeenCalledWith(
      expect.objectContaining({
        input_type: 'document',
        file_name: 'notes.txt',
        content: btoa('Acme ships to Reno.'),
      }),
      expect.any(AbortSignal),
    )

    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(await screen.findByText('ready')).toBeInTheDocument()
    expect(screen.getByText('Processed: passages are searchable.')).toBeInTheDocument()
    expect(api.documentStatus).toHaveBeenCalledWith('doc_1', expect.any(AbortSignal))

    // Finished: no more polling.
    await act(() => vi.advanceTimersByTimeAsync(6000))
    expect(api.documentStatus).toHaveBeenCalledTimes(2)
  })

  it('rejects files over 10 MB before sending anything', async () => {
    await renderPage(fakeApi())

    fireEvent.click(screen.getByRole('tab', { name: 'Document' }))
    const big = new File(['x'], 'huge.pdf', { type: 'application/pdf' })
    Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 })
    fireEvent.change(screen.getByLabelText(/^File/), { target: { files: [big] } })

    expect(screen.getByRole('alert')).toHaveTextContent('files are limited to 10.0 MB')
    expect(previewButton()).toBeDisabled()
  })
})

function status(name: string, finished: boolean, message: string): DocumentStatus {
  return {
    doc_id: 'doc_1',
    status: name,
    finished,
    chunks: finished ? 2 : 0,
    keywords: finished ? 5 : 0,
    created_at: null,
    updated_at: null,
    message,
  }
}
