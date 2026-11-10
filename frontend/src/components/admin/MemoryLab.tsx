import { useEffect, useState, type ReactNode } from 'react'
import type { PromotionApi } from '@/api/promotion'
import PromotionJob from '@/components/admin/PromotionJob'
import {
  labApi,
  type LabAction,
  type LabApi,
  type LabCounts,
  type LabRunRequest,
} from '@/api/lab'
import {
  setLabResult,
  useLabResults,
  type LabResult,
} from '@/components/admin/labResults'
import { isAbort, messageOf } from '@/components/capture/format'

const LABELS: Record<LabAction, string> = {
  consolidate: 'Consolidate',
  elaborate: 'Elaborate',
  reflect: 'Reflect',
}

type Scopes = Record<LabAction, string>

/**
 * Memory jobs: trigger consolidation, elaboration or reflection by hand, each
 * on the scope picked next to its button, and see what it did right under it
 * (standup 2026-11-04).
 */
export default function MemoryLab({
  api = labApi,
  promotionApi,
}: {
  api?: LabApi
  promotionApi?: PromotionApi
}) {
  const [options, setOptions] = useState<string[] | null>(null)
  // Each job's own scope; '' until the list has loaded.
  const [scopes, setScopes] = useState<Scopes>({
    consolidate: '',
    elaborate: '',
    reflect: '',
  })
  const [question, setQuestion] = useState('')
  const [persist, setPersist] = useState(false)
  const [running, setRunning] = useState<LabAction | null>(null)
  const [errors, setErrors] = useState<Partial<Record<LabAction, string>>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const results = useLabResults()

  useEffect(() => {
    const controller = new AbortController()
    api
      .scopes(controller.signal)
      .then((found) => {
        setOptions(found)
        const first = found[0] ?? ''
        setScopes((current) => ({
          consolidate: current.consolidate || first,
          elaborate: current.elaborate || first,
          reflect: current.reflect || first,
        }))
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setLoadError(messageOf(e))
      })
    return () => controller.abort()
  }, [api])

  const ready = (action: LabAction) => scopes[action] !== '' && running === null

  const run = async (request: Omit<LabRunRequest, 'scope'>) => {
    if (!ready(request.action)) return
    const full: LabRunRequest = { scope: scopes[request.action], ...request }
    setRunning(request.action)
    setErrors((all) => ({ ...all, [request.action]: undefined }))
    try {
      setLabResult(full, await api.run(full))
    } catch (e) {
      setErrors((all) => ({ ...all, [request.action]: messageOf(e) }))
    } finally {
      setRunning(null)
    }
  }

  const scopePicker = (action: LabAction) => (
    <label className="lab-scope">
      <span className="visually-hidden">Scope</span>
      <select
        value={scopes[action]}
        onChange={(e) => setScopes((all) => ({ ...all, [action]: e.target.value }))}
        disabled={options === null || running !== null}
      >
        {options?.map((path) => (
          <option key={path} value={path}>
            {path}
          </option>
        ))}
      </select>
    </label>
  )

  const card = (action: LabAction, description: string, controls: ReactNode) => (
    <section className="lab-job" aria-label={LABELS[action]}>
      <div className="lab-job-head">
        {scopePicker(action)}
        {controls}
      </div>
      <p className="admin-muted lab-job-desc">{description}</p>
      {running === action && (
        <output className="lab-running">
          <span className="ask-spinner" aria-hidden="true" /> Running… this can take a
          minute.
        </output>
      )}
      {errors[action] && (
        <div className="error" role="alert">
          <p>{errors[action]}</p>
        </div>
      )}
      {results[action] && <ResultPanel result={results[action]} />}
    </section>
  )

  return (
    <section className="panel lab" aria-labelledby="memory-jobs-title">
      <h2 id="memory-jobs-title">Memory jobs</h2>
      <p className="admin-muted">
        Pick a scope next to a job and trigger it. Each job runs with a key that can read
        and write only that scope, and its result shows below its button, with fact counts
        before and after.
      </p>
      {loadError && (
        <div className="error" role="alert">
          <p>{loadError}</p>
        </div>
      )}

      <div className="lab-jobs">
        {card(
          'consolidate',
          'Pools the facts in the scope into observations: creates, updates or supersedes them.',
          <>
            <button
              type="button"
              className="btn"
              disabled={!ready('consolidate')}
              onClick={() => void run({ action: 'consolidate', dry_run: false })}
            >
              Consolidate
            </button>
          </>,
        )}

        {card(
          'elaborate',
          'Links the entities in the scope to each other with new relations, one entity at a time.',
          <>
            <button
              type="button"
              className="btn"
              disabled={!ready('elaborate')}
              onClick={() => void run({ action: 'elaborate', dry_run: false })}
            >
              Elaborate
            </button>
          </>,
        )}

        {card(
          'reflect',
          'Answers a synthesis question from the scope; can save its insights as new facts.',
          <>
            <label className="lab-question">
              <span className="visually-hidden">Question</span>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What do we know about our carriers?"
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              className="btn"
              disabled={!ready('reflect') || !question.trim()}
              onClick={() =>
                void run({ action: 'reflect', query: question.trim(), persist })
              }
            >
              Reflect
            </button>
            <label className="lab-check">
              <input
                type="checkbox"
                checked={persist}
                onChange={(e) => setPersist(e.target.checked)}
              />
              Save insights as facts
            </label>
          </>,
        )}

        <PromotionJob api={promotionApi} />
      </div>
    </section>
  )
}

/** "+2 consolidation, +1 elaboration": what each origin gained or lost. */
function sourceChange(before: LabCounts, after: LabCounts): string {
  const kinds = new Set([
    ...Object.keys(before.by_source),
    ...Object.keys(after.by_source),
  ])
  return [...kinds]
    .map((k) => [k, (after.by_source[k] ?? 0) - (before.by_source[k] ?? 0)] as const)
    .filter(([, d]) => d !== 0)
    .map(([k, d]) => `${d > 0 ? '+' : ''}${d} ${k}`)
    .join(', ')
}

const arrow = (label: string, a: number, b: number) => `${label} ${a} → ${b}`

function ResultPanel({ result }: { result: LabResult }) {
  const { request, run } = result
  const mode = request.dry_run
    ? 'Preview'
    : request.action === 'reflect' && !request.persist
      ? 'Not saved'
      : 'Saved'
  const change = sourceChange(run.before, run.after)
  const summary = Object.entries(run.outcome.summary)
    .map(([k, v]) => `${k} ${v}`)
    .join(' · ')
  const at = new Date(run.ran_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <details className="lab-result" open aria-label={`Result: ${LABELS[run.action]}`}>
      <summary>
        Result · {mode} · {run.scope ?? 'whole context'} ·{' '}
        {(run.latency_ms / 1000).toFixed(1)} s · {at}
      </summary>
      <div className="lab-result-body">
        {summary && <p className="lab-summary">{summary}</p>}
        <p className="mono lab-counts">
          {arrow('entities', run.before.entities, run.after.entities)} ·{' '}
          {arrow('attributes', run.before.attributes, run.after.attributes)} ·{' '}
          {arrow('relations', run.before.relations, run.after.relations)}
          {change && <span className="lab-change"> ({change})</span>}
        </p>
        {run.outcome.text && <p className="lab-text">{run.outcome.text}</p>}
        {run.outcome.items.length ? (
          <ul className="lab-items">
            {run.outcome.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="admin-muted">Nothing to list.</p>
        )}
        {!!run.outcome.trace_ids.length && (
          <p className="mono admin-muted lab-trace">
            trace {run.outcome.trace_ids.slice(0, 3).join(', ')}
            {run.outcome.trace_ids.length > 3
              ? ` +${run.outcome.trace_ids.length - 3}`
              : ''}
          </p>
        )}
      </div>
    </details>
  )
}
