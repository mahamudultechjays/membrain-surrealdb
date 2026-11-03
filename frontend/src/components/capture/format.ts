import { ApiError } from '@/api/client'

/** "1.2 MB", "340 KB" or "12 B": enough precision to compare against the 10 MB limit. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

export function formatCount(n: number): string {
  return n.toLocaleString('en-US')
}

/** "1 fact", "3 facts". */
export function plural(n: number, word: string): string {
  return `${formatCount(n)} ${word}${n === 1 ? '' : 's'}`
}

/**
 * Corrections arrive as JSON strings like {"key":"lead_time","from":"10","to":"18 days"}.
 * Agent Memory's shape is not guaranteed, so anything else is shown as the raw text.
 */
export function describeCorrection(raw: string): string {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      const { key, from, to } = parsed as Record<string, unknown>
      if (key != null && to != null) {
        return `${String(key)}: ${from == null ? '—' : String(from)} → ${String(to)}`
      }
    }
  } catch {
    // Not JSON: fall through to the raw text.
  }
  return raw
}

/** The backend marks hedged facts with a note "uncertain: <reason>". */
export function uncertaintyReason(note: string | null): string | null {
  if (!note?.toLowerCase().startsWith('uncertain')) return null
  return note.replace(/^uncertain:?\s*/i, '') || 'the speaker hedged'
}

/** The file's bytes as base64, without the "data:...;base64," prefix the backend doesn't want. */
export function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = String(reader.result)
      resolve(dataUrl.slice(dataUrl.indexOf(',') + 1))
    }
    reader.onerror = () => reject(reader.error ?? new Error('Could not read the file.'))
    reader.readAsDataURL(file)
  })
}

/** ApiError already carries FastAPI's `detail`; anything else falls back to its message. */
export function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

export function statusOf(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
