import { useEffect, useState } from 'react'
import type { CaptureApi, DocumentStatus } from '@/api/capture'
import { isAbort, messageOf, statusOf } from '@/components/capture/format'

const POLL_MS = 2000
/** Agent Memory usually finishes in seconds; past this something is stuck, so stop asking. */
const GIVE_UP_MS = 10 * 60 * 1000

interface Poll {
  latest: DocumentStatus | null
  error: string | null
  gaveUp: boolean
}

/**
 * Polls the upload's status until Agent Memory says it is finished. Stops on
 * unmount, so the page remounts this (keyed by preview) for every new preview.
 */
function useDocumentStatus(api: CaptureApi, docId: string): Poll {
  const [poll, setPoll] = useState<Poll>({
    latest: null,
    error: null,
    gaveUp: false,
  })

  useEffect(() => {
    const controller = new AbortController()
    const started = Date.now()
    let timer: ReturnType<typeof setTimeout> | undefined

    const check = async () => {
      try {
        const latest = await api.documentStatus(docId, controller.signal)
        setPoll((p) => ({ ...p, latest, error: null }))
        if (latest.finished) return
      } catch (error) {
        if (controller.signal.aborted || isAbort(error)) return
        setPoll((p) => ({ ...p, error: messageOf(error) }))
        // A 4xx won't fix itself (unknown document, wrong scope); a 5xx might.
        const status = statusOf(error)
        if (status !== null && status < 500) return
      }
      if (Date.now() - started >= GIVE_UP_MS) {
        setPoll((p) => ({ ...p, gaveUp: true }))
        return
      }
      timer = setTimeout(() => void check(), POLL_MS)
    }

    void check()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [api, docId])

  return poll
}

interface Props {
  api: CaptureApi
  docId: string
}

export default function DocumentStatusPanel({ api, docId }: Props) {
  const { latest, error, gaveUp } = useDocumentStatus(api, docId)
  const ready = latest?.finished && latest.status === 'ready'
  const tone = !latest ? undefined : latest.finished ? (ready ? 'good' : 'bad') : 'note'
  const working = !latest?.finished && !error && !gaveUp

  return (
    <section className="panel capture-doc" aria-labelledby="capture-doc-heading">
      <div className="capture-doc-head">
        <h3 id="capture-doc-heading">Document processing</h3>
        {latest && (
          <span className="tag" data-tone={tone}>
            {latest.status}
          </span>
        )}
      </div>
      {/* Only the outcome is announced; the counts and debug detail stay out of the way. */}
      <div aria-live="polite" className="capture-doc-body">
        {!error && (
          <p className="capture-doc-status">
            {working && <span className="capture-doc-spinner" aria-hidden="true" />}
            <span>{latest?.message ?? 'Checking the upload…'}</span>
            {ready && (
              <span className="capture-muted">
                · {latest.chunks} {latest.chunks === 1 ? 'chunk' : 'chunks'}
              </span>
            )}
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {gaveUp && (
          <p className="note">
            Taking longer than expected, so we stopped checking. Agent Memory may still
            finish; preview again later to see the status.
          </p>
        )}
      </div>
    </section>
  )
}
