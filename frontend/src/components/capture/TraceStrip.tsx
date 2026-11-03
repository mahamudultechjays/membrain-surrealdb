export interface TraceEntry {
  /** What was called, e.g. "POST /api/v1/capture/preview · infer=preview". */
  call: string
  traceId: string | null
  ms: number
  /** HTTP status of a failed call, or "ok". */
  outcome: string
}

/**
 * The calls this screen made, folded away by default: trace ids match the
 * backend's [CAPTURE] log lines in a demo, but mean nothing to most users.
 */
export default function TraceStrip({ entries }: { entries: TraceEntry[] }) {
  return (
    <details className="capture-trace" aria-label="API calls">
      <summary className="capture-trace-title">
        Developer details{entries.length > 0 && ` · ${entries.length}`}
      </summary>
      {entries.length === 0 ? (
        <p className="mono">No API calls yet.</p>
      ) : (
        <ul>
          {entries.map((entry, index) => (
            <li key={index} className="mono">
              {entry.call} · {entry.outcome} · trace {entry.traceId ?? 'none'} ·{' '}
              {Math.round(entry.ms)} ms
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}
