import { useEffect, useState } from 'react'

/** Recall is slow (about 10 s live), so show that time is passing and offer a way out. */
export default function AskLoading({ onCancel }: { onCancel: () => void }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      500,
    )
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="panel ask-loading">
      <span className="ask-spinner" aria-hidden="true" />
      {/* Announced once; the ticking seconds are hidden so they aren't read out every second. */}
      <output className="ask-loading-text">
        <strong>
          Recalling from each layer… <span aria-hidden="true">{seconds} s</span>
        </strong>
        <span className="ask-muted">Recall can take about 10 s.</span>
      </output>
      <button type="button" className="btn-secondary" onClick={onCancel}>
        Cancel
      </button>
    </div>
  )
}
