import { getHealth, getReadiness } from '@/api/health'
import { useAsync } from '@/hooks/useAsync'

export default function HealthStatus() {
  const health = useAsync(getHealth)
  const readiness = useAsync(getReadiness)

  const api =
    health.status === 'loading'
      ? 'checking…'
      : health.status === 'success'
        ? `ok (v${health.data.version}, ${health.data.environment})`
        : 'unreachable'

  const database =
    readiness.status === 'loading'
      ? 'checking…'
      : readiness.status === 'success'
        ? 'ok'
        : 'unavailable'

  return (
    <section aria-labelledby="health-heading">
      <h2 id="health-heading">Service status</h2>
      <ul className="status">
        <li>
          <span>API</span>
          <span data-state={stateOf(health.status)}>{api}</span>
        </li>
        <li>
          <span>SurrealDB</span>
          <span data-state={stateOf(readiness.status)}>{database}</span>
        </li>
      </ul>
    </section>
  )
}

function stateOf(status: 'loading' | 'success' | 'error') {
  return status === 'success' ? 'ok' : status === 'error' ? 'down' : 'pending'
}
