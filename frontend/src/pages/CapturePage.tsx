import { useEffect, useRef, useState } from 'react'
import {
  MAX_TEXT_CHARS,
  captureApi,
  type CaptureApi,
  type CaptureConfig,
  type CaptureExtractRequest,
  type CaptureExtractResponse,
  type CapturePreviewRequest,
  type CapturePreviewResponse,
  type CaptureStoreResponse,
  type MemoryCategory,
  type StoreMode,
} from '@/api/capture'
import type { Grant, Me } from '@/api/auth'
import { spaceName } from '@/components/ask/layers'
import CaptureInput, { type InputTab } from '@/components/capture/CaptureInput'
import CaptureSettings from '@/components/capture/CaptureSettings'
import DocumentStatusPanel from '@/components/capture/DocumentStatusPanel'
import ElapsedSeconds from '@/components/capture/ElapsedSeconds'
import PreviewResult, { type StoreState } from '@/components/capture/PreviewResult'
import { choicesToSend, keptIds, type EntityChoices } from '@/components/capture/keep'
import StepIndicator from '@/components/capture/StepIndicator'
import StoreResult from '@/components/capture/StoreResult'
import TraceStrip, { type TraceEntry } from '@/components/capture/TraceStrip'
import {
  isAbort,
  messageOf,
  readFileAsBase64,
  statusOf,
} from '@/components/capture/format'
import HeaderSlot from '@/components/HeaderSlot'
import ScopePicker, { type PickerOption } from '@/components/ScopePicker'
import '@/pages/capture.css'

type PreviewState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'done'; data: CapturePreviewResponse; stored: CaptureStoreResponse | null }

/** Re-extract everything: one call that extracts and stores, with no preview. */
type ExtractState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'done'; data: CaptureExtractResponse }

/** Enough to see the last previews and stores without the strip taking over. */
const MAX_TRACES = 6

interface Props {
  me: Me
  api?: CaptureApi
}

/** "My space", the owner's name for someone else's space, or "Team ops". */
function scopeOption(grant: Grant): PickerOption {
  return { id: grant.scope_path, name: spaceName(grant), detail: grant.scope_path }
}

export default function CapturePage({ me, api = captureApi }: Props) {
  // Only scopes this user may write; the personal one comes first.
  const writable = me.grants
    .filter((g) => g.access === 'write')
    .sort((a, b) => Number(b.layer === 'personal') - Number(a.layer === 'personal'))
  // Null until the user picks: until then, their personal scope.
  const [chosenScope, setChosenScope] = useState<string | null>(null)
  const [tab, setTab] = useState<InputTab>('text')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<StoreMode>('triples')
  const [category, setCategory] = useState<MemoryCategory | null>(null)
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' })
  const [kept, setKept] = useState<ReadonlySet<string>>(new Set())
  const [choices, setChoices] = useState<EntityChoices>({})
  const [store, setStore] = useState<StoreState>({ status: 'idle' })
  const [extracted, setExtracted] = useState<ExtractState>({ status: 'idle' })
  const [traces, setTraces] = useState<TraceEntry[]>([])
  // Bumped on reset so the file input forgets its file.
  const [inputKey, setInputKey] = useState(0)

  // One in-flight call of each kind; a newer one (or leaving the page) aborts the older.
  const previewCall = useRef<AbortController | null>(null)
  const storeCall = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      previewCall.current?.abort()
      storeCall.current?.abort()
    },
    [],
  )

  const scope = chosenScope ?? writable[0]?.scope_path ?? null

  const overLimit = text.length > MAX_TEXT_CHARS
  const hasInput = tab === 'text' ? text.trim() !== '' && !overLimit : file !== null
  const previewing = preview.status === 'loading'
  const extracting = extracted.status === 'loading'
  // Re-extract everything skips the preview: the store runs extraction again anyway.
  const direct = mode === 'full'
  const config: CaptureConfig = { mode, memory_category: category }

  const trace = (entry: TraceEntry) =>
    setTraces((all) => [...all, entry].slice(-MAX_TRACES))

  const clearPreview = () => {
    previewCall.current?.abort()
    storeCall.current?.abort()
    setPreview({ status: 'idle' })
    setStore({ status: 'idle' })
    setExtracted({ status: 'idle' })
    setKept(new Set())
    setChoices({})
  }

  // A preview is only for "only the facts I keep", and a direct store's result
  // belongs to the mode that made it, so switching starts over (the input stays).
  const changeMode = (next: StoreMode) => {
    if (next === mode) return
    setMode(next)
    clearPreview()
  }

  /** The input as the API takes it: text, or the file as base64. */
  async function inputBody(): Promise<CaptureExtractRequest> {
    if (tab === 'document' && file) {
      const content = await readFileAsBase64(file)
      return { scope, input_type: 'document', content, file_name: file.name }
    }
    return { scope, input_type: 'text', content: text }
  }

  async function runExtract() {
    if (!scope || !hasInput) return
    previewCall.current?.abort()
    storeCall.current?.abort()
    const controller = new AbortController()
    storeCall.current = controller
    setExtracted({ status: 'loading' })

    const call =
      tab === 'text'
        ? 'POST /api/v1/capture/extract · infer=full'
        : 'POST /api/v1/capture/extract · documents.upload + infer=full'
    const started = performance.now()
    try {
      const data = await api.extract(await inputBody(), controller.signal)
      if (controller.signal.aborted) return
      setExtracted({ status: 'done', data })
      trace({
        call,
        traceId: data.trace_id,
        ms: performance.now() - started,
        outcome: 'ok',
      })
    } catch (error) {
      if (controller.signal.aborted || isAbort(error)) return
      setExtracted({ status: 'error', message: messageOf(error) })
      trace({
        call,
        traceId: null,
        ms: performance.now() - started,
        outcome: String(statusOf(error) ?? 'failed'),
      })
    }
  }

  // A preview belongs to one scope: storing it as someone else would get a 403.
  const changeScope = (ids: string[]) => {
    const next = ids[0] ?? null
    if (next === scope) return
    setChosenScope(next)
    clearPreview()
  }

  async function runPreview() {
    if (!scope || !hasInput) return
    previewCall.current?.abort()
    storeCall.current?.abort()
    const controller = new AbortController()
    previewCall.current = controller
    setPreview({ status: 'loading' })
    setStore({ status: 'idle' })

    const call =
      tab === 'text'
        ? 'POST /api/v1/capture/preview · infer=preview'
        : 'POST /api/v1/capture/preview · documents.upload + infer=preview'
    const started = performance.now()
    try {
      const body: CapturePreviewRequest = { ...(await inputBody()), config }
      const data = await api.preview(body, controller.signal)
      if (controller.signal.aborted) return
      setPreview({ status: 'done', data, stored: null })
      setKept(new Set(data.extracted.filter((f) => f.storable).map((f) => f.id)))
      setChoices({})
      trace({
        call,
        traceId: data.trace_id,
        ms: performance.now() - started,
        outcome: 'ok',
      })
    } catch (error) {
      if (controller.signal.aborted || isAbort(error)) return
      setPreview({ status: 'error', message: messageOf(error) })
      trace({
        call,
        traceId: null,
        ms: performance.now() - started,
        outcome: String(statusOf(error) ?? 'failed'),
      })
    }
  }

  async function runStore() {
    if (preview.status !== 'done') return
    const { data } = preview
    storeCall.current?.abort()
    const controller = new AbortController()
    storeCall.current = controller
    setStore({ status: 'loading' })

    const call = `POST /api/v1/capture/store · infer=${mode === 'triples' ? 'triples' : 'full'}`
    const started = performance.now()
    try {
      const stored = await api.store(
        {
          preview_id: data.preview_id,
          scope: data.scope,
          kept: keptIds(data, mode, kept, choices),
          config,
          entity_choices: choicesToSend(data, mode, kept, choices),
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      setPreview({ status: 'done', data, stored })
      setStore({ status: 'idle' })
      trace({
        call,
        traceId: stored.trace_id,
        ms: performance.now() - started,
        outcome: 'ok',
      })
    } catch (error) {
      if (controller.signal.aborted || isAbort(error)) return
      const status = statusOf(error)
      setStore({ status: 'error', message: messageOf(error), expired: status === 404 })
      trace({
        call,
        traceId: null,
        ms: performance.now() - started,
        outcome: String(status ?? 'failed'),
      })
    }
  }

  // Picking an entity also ticks the fact; clearing the pick makes it unkeepable again.
  const chooseEntity = (id: string, entity: string) => {
    setChoices((current) => {
      const next = { ...current }
      if (entity) next[id] = entity
      else delete next[id]
      return next
    })
    if (entity) setKept((current) => new Set(current).add(id))
  }

  const toggleKept = (id: string) =>
    setKept((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })

  const reset = () => {
    clearPreview()
    setText('')
    setFile(null)
    setInputKey((k) => k + 1)
  }

  const step = direct
    ? extracted.status === 'done'
      ? 'stored'
      : 'input'
    : preview.status === 'done'
      ? preview.stored
        ? 'stored'
        : 'preview'
      : 'input'

  return (
    <main className="page capture">
      <header className="page-head">
        <h1>Capture</h1>
        <p>
          {direct
            ? 'Re-extract everything stores straight away: Agent Memory reads the input and saves all it finds, with no preview.'
            : 'What you type is previewed first, so you see what Agent Memory would extract. Nothing is saved until you store it.'}
        </p>
      </header>

      <StepIndicator current={step} skipPreview={direct} />

      <div className="capture-grid">
        <section className="panel capture-compose" aria-label="Input">
          {writable.length === 0 ? (
            <p className="error" role="alert">
              You have no scope you can write to. Ask an admin for one.
            </p>
          ) : (
            <HeaderSlot>
              <ScopePicker
                options={writable.map(scopeOption)}
                value={scope ? [scope] : []}
                onChange={changeScope}
                label="Capture to"
              />
            </HeaderSlot>
          )}

          <CaptureInput
            key={inputKey}
            tab={tab}
            onTabChange={setTab}
            text={text}
            onTextChange={setText}
            file={file}
            onFileChange={setFile}
          />

          <div className="capture-actions">
            {direct ? (
              <button
                type="button"
                className="btn"
                disabled={!scope || !hasInput || extracting}
                onClick={() => void runExtract()}
              >
                Store
              </button>
            ) : (
              <button
                type="button"
                className="btn"
                disabled={!scope || !hasInput || previewing}
                onClick={() => void runPreview()}
              >
                Preview
              </button>
            )}
            {previewing && <ElapsedSeconds label="Agent Memory is extracting" />}
            {extracting && (
              <ElapsedSeconds label="Agent Memory is extracting and storing" />
            )}
          </div>
        </section>

        <section className="panel" aria-label="Settings">
          <CaptureSettings
            mode={mode}
            onModeChange={changeMode}
            category={category}
            onCategoryChange={setCategory}
          />
        </section>
      </div>

      <div className="capture-results">
        {direct && extracted.status === 'idle' && (
          <p className="empty">
            Press Store and Agent Memory extracts everything in the input and saves it.
            This mode has no preview.
          </p>
        )}
        {extracting && (
          <p className="empty">
            Agent Memory is extracting and storing. This usually takes a few seconds.
          </p>
        )}
        {extracted.status === 'error' && (
          <p className="error" role="alert">
            Store failed: {extracted.message}
          </p>
        )}
        {extracted.status === 'done' && (
          <>
            {extracted.data.truncated && (
              <p className="capture-warn" role="alert">
                {extracted.data.truncated_reason ??
                  'Only part of the document was extracted.'}{' '}
                Facts come from those words; the whole document is uploaded and
                searchable.
              </p>
            )}
            <StoreResult
              result={extracted.data}
              scope={extracted.data.scope}
              onReset={reset}
            />
            {extracted.data.doc_id && (
              <DocumentStatusPanel
                key={extracted.data.stored_id}
                api={api}
                docId={extracted.data.doc_id}
              />
            )}
          </>
        )}
        {!direct && preview.status === 'idle' && (
          <p className="empty">
            Press Preview to see what Agent Memory would extract. Nothing is saved until
            you store it.
          </p>
        )}
        {previewing && (
          <p className="empty">
            Agent Memory is reading the input. A preview usually takes a few seconds.
          </p>
        )}
        {preview.status === 'error' && (
          <p className="error" role="alert">
            Preview failed: {preview.message}
          </p>
        )}
        {preview.status === 'done' &&
          (preview.stored ? (
            <StoreResult
              result={preview.stored}
              scope={preview.data.scope}
              onReset={reset}
            />
          ) : (
            <PreviewResult
              preview={preview.data}
              mode={mode}
              kept={kept}
              onToggle={toggleKept}
              choices={choices}
              onChoose={chooseEntity}
              category={category}
              store={store}
              onStore={() => void runStore()}
              onPreviewAgain={() => void runPreview()}
            />
          ))}
        {preview.status === 'done' && preview.data.doc_id && (
          <DocumentStatusPanel
            key={preview.data.preview_id}
            api={api}
            docId={preview.data.doc_id}
          />
        )}
      </div>

      <TraceStrip entries={traces} />
    </main>
  )
}
