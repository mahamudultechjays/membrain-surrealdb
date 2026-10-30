import { getHealth, getReadiness, type AgentMemoryStatus } from '@/api/health'
import { useAsync, type AsyncState } from '@/hooks/useAsync'

const MEMORY_LABELS: Record<AgentMemoryStatus, string> = {
  ok: 'ok',
  unavailable: 'unavailable',
  not_configured: 'not configured (set AGENT_MEMORY_* in .env)',
}

export default function HealthStatus() {
  const health = useAsync(getHealth)
  const readiness = useAsync(getReadiness)

  const api =
    health.status === 'loading'
      ? 'checking…'
      : health.status === 'success'
        ? `ok (v${health.data.version}, ${health.data.environment})`
        : 'unreachable'

  const memory =
    readiness.status === 'loading'
      ? 'checking…'
      : readiness.status === 'success'
        ? MEMORY_LABELS[readiness.data.agent_memory]
        : 'unknown (API unreachable)'

  return (
    <section aria-labelledby="health-heading">
      <h2 id="health-heading">Service status</h2>
      <ul className="status">
        <li>
          <span>API</span>
          <span data-state={stateOf(health)}>{api}</span>
        </li>
        <li>
          <span>Agent Memory</span>
          <span data-state={memoryStateOf(readiness)}>{memory}</span>
        </li>
      </ul>
    </section>
  )
}

function stateOf(state: AsyncState<unknown>) {
  return state.status === 'success' ? 'ok' : state.status === 'error' ? 'down' : 'pending'
}

function memoryStateOf(state: AsyncState<{ agent_memory: AgentMemoryStatus }>) {
  if (state.status !== 'success') return stateOf(state)
  return state.data.agent_memory === 'ok' ? 'ok' : 'down'
}
