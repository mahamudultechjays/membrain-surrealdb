import { useCallback, useEffect, useRef, useState } from 'react'

import { promotionApi, type PromotionApi, type PromotionStatus } from '@/api/promotion'
import { messageOf, statusOf } from '@/components/capture/format'

/**
 * Admin › Lab: run the promotion job by hand, so candidates pile up for review
 * without waiting for the schedule. Review happens on Admin › Promotion.
 */
export default function PromotionJob({ api = promotionApi }: { api?: PromotionApi }) {
  const [status, setStatus] = useState<PromotionStatus | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [started, setStarted] = useState(false)
  const alive = useRef(true)

  const read = useCallback(
    () =>
      api
        .status()
        .then((s) => {
          if (alive.current) setStatus(s)
          return s
        })
        .catch((error: unknown) => {
          if (alive.current) setFailure(messageOf(error))
          return null
        }),
    [api],
  )

  useEffect(() => {
    alive.current = true
    void read()
    return () => {
      alive.current = false
    }
  }, [read])

  // While a run is going, check back every few seconds.
  const running = status?.running ?? false
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => void read(), 3000)
    return () => window.clearInterval(timer)
  }, [running, read])

  const run = () => {
    setFailure(null)
    api
      .run()
      .then(() => {
        setStarted(true)
        return read()
      })
      .catch((error: unknown) =>
        setFailure(
          statusOf(error) === 409 ? 'Promotion is already running.' : messageOf(error),
        ),
      )
  }

  const last = status?.last_run
  const open = status?.items.filter((i) => i.status === 'open').length ?? 0
  return (
    <section className="lab-job" aria-labelledby="lab-promotion-title">
      <div className="lab-job-head">
        <h3 id="lab-promotion-title">Promotion</h3>
        <button type="button" className="btn" disabled={!status || running} onClick={run}>
          {running ? 'Running…' : 'Run promotion'}
        </button>
      </div>
      <p className="admin-muted lab-job-desc">
        Lists every personal scope&apos;s facts, groups the new ones into topics with a
        small Claude model, rescores them and lists those that reach the team threshold
        for review.
      </p>
      {status && !status.model_configured && (
        <p className="error">
          ANTHROPIC_API_KEY is not set: new facts are listed but not grouped.
        </p>
      )}
      {running && (
        <output className="lab-running">
          <span className="ask-spinner" aria-hidden="true" /> Running… listing and
          grouping can take a minute.
        </output>
      )}
      {failure && (
        <div className="error" role="alert">
          <p>{failure}</p>
        </div>
      )}
      {last && (started || last.finished_at) && !running && (
        <div className="lab-result">
          <p>
            Last run{' '}
            {last.finished_at ? new Date(last.finished_at).toLocaleTimeString() : '—'}:{' '}
            {last.listed} facts listed, {last.new} new, {last.grouped} grouped
            {last.new_topics ? ` (${last.new_topics} new topics)` : ''}, {last.left} left
            to group, {last.opened} listed, {last.dropped} dropped.
          </p>
          {last.error && <p className="error">Stopped early: {last.error}</p>}
          <p>
            {open} open for review · <a href="#/admin/promotion">Review in Promotion</a>
          </p>
        </div>
      )}
    </section>
  )
}
