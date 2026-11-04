import type { CapturePreviewResponse, MemoryCategory, StoreMode } from '@/api/capture'
import ElapsedSeconds from '@/components/capture/ElapsedSeconds'
import FactTable from '@/components/capture/FactTable'
import { describeCorrection, plural } from '@/components/capture/format'
import { keptIds, type EntityChoices } from '@/components/capture/keep'

export type StoreState =
  | { status: 'idle' }
  | { status: 'loading' }
  /** `expired`: the backend lost the preview (404), so only a new preview helps. */
  | { status: 'error'; message: string; expired: boolean }

interface Props {
  preview: CapturePreviewResponse
  mode: StoreMode
  kept: ReadonlySet<string>
  onToggle: (id: string) => void
  choices: EntityChoices
  onChoose: (id: string, entity: string) => void
  /** The Memory category setting, shown in place of each fact's own. */
  category: MemoryCategory | null
  store: StoreState
  onStore: () => void
  onPreviewAgain: () => void
}

export default function PreviewResult({
  preview,
  mode,
  kept,
  onToggle,
  choices,
  onChoose,
  category,
  store,
  onStore,
  onPreviewAgain,
}: Props) {
  const { stats } = preview
  const storing = store.status === 'loading'
  const keptCount = keptIds(preview, mode, kept, choices).length
  const canStore = mode === 'full' || keptCount > 0

  return (
    <section className="panel capture-preview" aria-labelledby="capture-preview-heading">
      <div className="capture-result-head">
        <h2 id="capture-preview-heading">Preview · nothing stored yet</h2>
        <span className="mono capture-muted">{preview.preview_id}</span>
      </div>
      <p className="capture-stats">
        <b>{plural(stats.total, 'fact')}</b> · <b>{stats.uncertain}</b> uncertain ·{' '}
        <b>{plural(stats.corrections, 'correction')}</b>
      </p>
      <p className="capture-hint">
        Agent Memory reports no per-fact confidence and no token cost, so neither is
        shown.
      </p>

      {preview.truncated && (
        <p className="capture-warn" role="alert">
          {preview.truncated_reason ?? 'Only part of the document was previewed.'} Paste
          the text in the Text tab (up to 20,000 characters) to preview all of it.
        </p>
      )}

      <FactTable
        facts={preview.extracted}
        mode={mode}
        kept={kept}
        onToggle={onToggle}
        entities={preview.entities}
        choices={choices}
        onChoose={onChoose}
        category={category}
        disabled={storing}
      />

      {preview.corrections.length > 0 && (
        <div className="capture-corrections">
          <h3>Corrections</h3>
          <ul>
            {preview.corrections.map((raw, index) => (
              <li key={index} className="mono">
                {describeCorrection(raw)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="capture-actions">
        <button
          type="button"
          className="btn"
          disabled={!canStore || storing}
          onClick={onStore}
        >
          {mode === 'full' ? 'Store everything' : `Store ${plural(keptCount, 'fact')}`}
        </button>
        {storing && <ElapsedSeconds label="Storing" />}
      </div>
      {mode === 'full' ? (
        <p className="capture-hint">
          Full re-extraction ignores the ticks: Agent Memory stores everything it finds in
          the input.
        </p>
      ) : (
        !canStore && <p className="capture-hint">Tick at least one fact to store.</p>
      )}

      {store.status === 'error' &&
        (store.expired ? (
          <div className="error capture-expired" role="alert">
            <p>
              Preview expired (the backend keeps recent previews in memory only). Run
              preview again.
            </p>
            <button type="button" className="btn-secondary" onClick={onPreviewAgain}>
              Run preview again
            </button>
          </div>
        ) : (
          <p className="error" role="alert">
            {store.message}
          </p>
        ))}
    </section>
  )
}
