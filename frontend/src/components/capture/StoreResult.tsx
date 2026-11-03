import type { CaptureStoreResponse } from '@/api/capture'
import { plural } from '@/components/capture/format'

interface Props {
  result: CaptureStoreResponse
  scope: string
  onReset: () => void
}

export default function StoreResult({ result, scope, onReset }: Props) {
  return (
    <section className="panel capture-stored" aria-labelledby="capture-stored-heading">
      <div className="capture-result-head">
        <h2 id="capture-stored-heading">Stored in {scope}</h2>
        <span className="mono capture-muted">
          {plural(result.written, 'write')} · {result.stored_id}
        </span>
      </div>

      {result.created_facts.length ? (
        <table className="capture-table">
          <caption className="visually-hidden">Created facts</caption>
          <thead>
            <tr>
              <th scope="col">Entity</th>
              <th scope="col">Key</th>
              <th scope="col">Value</th>
              <th scope="col">Id</th>
            </tr>
          </thead>
          <tbody>
            {result.created_facts.map((fact, index) => (
              <tr key={fact.id ?? index}>
                <td data-label="Entity">{fact.entity}</td>
                <td data-label="Key" className="mono">
                  {fact.key}
                </td>
                <td data-label="Value">{fact.value}</td>
                <td data-label="Id" className="mono capture-muted">
                  {fact.id ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">Agent Memory reported no created facts.</p>
      )}

      {result.history.length > 0 && (
        <>
          <h3>Changed values</h3>
          <ul className="capture-history">
            {result.history.map((entry, index) => (
              <li key={index}>
                <span className="mono">
                  {entry.key ?? 'value'}: {entry.old_value ?? '—'} →{' '}
                  {entry.new_value ?? '—'}
                </span>{' '}
                <span className="mono capture-muted">· {entry.changed_at}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="capture-actions">
        <button type="button" className="btn-secondary" onClick={onReset}>
          Capture something else
        </button>
      </div>
    </section>
  )
}
