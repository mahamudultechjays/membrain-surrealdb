import { ApiError } from '@/api/client'
import {
  LARGE_DOCUMENT_WORDS,
  MAX_FILE_BYTES,
  MAX_TEXT_CHARS,
  type CaptureApi,
  type CaptureExtractRequest,
  type CapturePreviewResponse,
  type CaptureStoreResponse,
  type CreatedFact,
  type ExtractedFact,
  type HistoryEntry,
} from '@/api/capture'
import { currentUser, delay, newId, records, traceId } from '@/api/mock/backend'

const PREVIEW_WORDS = 500
const MAX_PREVIEWS = 200
const NO_ENTITY_NOTE = 'entity not known in preview; store with mode full'
const TRUNCATED_REASON = `Large document: preview shows first ${PREVIEW_WORDS} words only`

interface Correction {
  key: string
  from: string
  to: string
}

interface StoredPreview {
  response: CapturePreviewResponse
  text: string
  /** Entity, key and value per storable fact id. */
  triples: Map<string, { entity: string; key: string; value: string }>
  /** Key and value of facts with no entity, which the user may link to one. */
  unlinked: Map<string, { key: string; value: string }>
  entities: string[]
  corrections: Correction[]
}

const previews = new Map<string, StoredPreview>()
const documents = new Map<string, { uploadedAt: number; words: number }>()

const HEDGES = /\b(i think|maybe|probably|might|not sure|apparently)\b/i
const STATEMENT =
  /^(.+?)\s+(is|are|was|has|have|ships|takes|costs|moved to|owns)\s+(.+)$/i
const UP_FROM = /^(.+?)\s*,?\s*(?:up|down) from\s+(.+)$/i
const PRONOUN = /^(it|they|this|that|he|she)$/i

/**
 * A rough stand-in for Agent Memory's extraction: one fact per simple
 * "subject verb value" sentence. Good enough to exercise every UI state:
 * uncertain facts, corrections, and facts with no entity link.
 */
function extract(text: string) {
  const facts: {
    fact: string
    type: string
    note: string | null
    entity: string | null
    key: string
    value: string
  }[] = []
  const corrections: Correction[] = []
  const sentences = text
    .split(/(?<=[.!?])\s+|\n+/)
    .map((s) => s.trim().replace(/[.!?]+$/, ''))
    .filter((s) => s.split(/\s+/).length >= 3)

  for (const sentence of sentences) {
    const match = STATEMENT.exec(sentence.replace(HEDGES, '').trim())
    if (!match) continue
    const [, rawSubject = '', verb = '', rawValue = ''] = match
    const subject = rawSubject
      .replace(/^(the|our|my|a|an)\s+/i, '')
      .replace(/'s\s+.*$/, '')
      .toLowerCase()
    const possessed = /'s\s+(.+)$/.exec(rawSubject)?.[1]
    const key = (possessed ?? verb).toLowerCase().replace(/\s+/g, '_')
    let value = rawValue.trim()

    const changed = UP_FROM.exec(value)
    if (changed) {
      value = (changed[1] ?? value).trim()
      corrections.push({ key, from: (changed[2] ?? '').trim(), to: value })
    }

    const entity = PRONOUN.test(subject) ? null : subject
    const type = /\b(today|this week|now|currently)\b/i.test(sentence)
      ? 'context'
      : 'knowledge'
    const note = HEDGES.test(sentence)
      ? `uncertain: ${sentence.match(HEDGES)?.[0].toLowerCase()} — the speaker hedged`
      : entity
        ? null
        : NO_ENTITY_NOTE
    facts.push({
      fact: `${entity ?? '?'} · ${key} = ${value}`,
      type,
      note,
      entity,
      key,
      value,
    })
  }

  const entities = [
    ...new Set(facts.map((f) => f.entity).filter((e): e is string => e !== null)),
  ]
  for (const entity of entities.slice(0, 2)) {
    facts.push({
      fact: `${entity} · type = thing`,
      type: 'knowledge',
      note: null,
      entity,
      key: 'type',
      value: 'thing',
    })
  }
  return { facts, corrections }
}

function wordsOf(text: string) {
  return text.split(/\s+/).filter(Boolean)
}

function decodeDocument(content: string, fileName: string): string {
  let bytes: string
  try {
    bytes = atob(content)
  } catch {
    throw new ApiError(422, 'Document content must be base64.')
  }
  if (!bytes.length) throw new ApiError(422, 'The file is empty.')
  if (bytes.length > MAX_FILE_BYTES)
    throw new ApiError(413, 'Files are limited to 10 MB.')
  if (/\.pdf$/i.test(fileName)) {
    // The real backend reads the PDF's text; the mock can't, so it returns a stand-in.
    return `Acme Logistics ships to our Reno warehouse. Acme's lead time is 18 days, up from 10. The restocking fee is 15%. (Text the backend would read from ${fileName}.)`
  }
  if (!/\.(txt|md|text)$/i.test(fileName)) {
    throw new ApiError(415, 'Only PDF and plain-text files are supported.')
  }
  return new TextDecoder().decode(Uint8Array.from(bytes, (c) => c.charCodeAt(0)))
}

/** The scope a write goes to, as AccessService.write_scope decides it. */
function writeScope(requested: string | null | undefined): string {
  const writable = currentUser().grants.filter((g) => g.access === 'write')
  if (requested == null) {
    const personal = writable.find((g) => g.layer === 'personal')
    if (!personal) throw new ApiError(403, 'No personal scope to write to.')
    return personal.scope_path
  }
  const path = requested.replace(/^\/+|\/+$/g, '')
  if (!writable.some((g) => g.scope_path === path)) {
    throw new ApiError(403, `Not writable: ${path}`)
  }
  return path
}

/** The text extraction runs on, as the backend's _read_input reads it. */
function readInput(body: CaptureExtractRequest) {
  const scope = writeScope(body.scope)
  let text = body.content
  let source = 'text'
  let truncated = false
  let docId: string | null = null

  if (body.input_type === 'text') {
    if (text.length > MAX_TEXT_CHARS) {
      throw new ApiError(
        422,
        `Text is limited to ${MAX_TEXT_CHARS} characters; use the document tab.`,
      )
    }
  } else {
    const fileName = body.file_name || 'document'
    text = decodeDocument(text, fileName)
    const words = wordsOf(text)
    truncated = words.length > LARGE_DOCUMENT_WORDS
    if (truncated) text = words.slice(0, PREVIEW_WORDS).join(' ')
    docId = newId('doc')
    documents.set(docId, { uploadedAt: Date.now(), words: words.length })
    source = `document ${fileName}${truncated ? ' (first words)' : ''}`
  }
  return { scope, text, source, truncated, docId }
}

type Triple = { entity: string; key: string; value: string }

/** Records the facts in the mock store and builds the store response. */
function save(
  scope: string,
  written: Triple[],
  corrections: Correction[],
): CaptureStoreResponse {
  const created: CreatedFact[] = written.map((t) => {
    const id = newId('attribute')
    records.push({
      id,
      area: scope,
      kind: 'attribute',
      text: `${t.entity} · ${t.key} = ${t.value}`,
    })
    return { entity: t.entity, key: t.key, value: t.value, id }
  })
  const changedAt = new Date().toISOString().replace(/\.\d+Z$/, '+00:00')
  const history: HistoryEntry[] = corrections.map((c) => ({
    fact_id: created.find((f) => f.key === c.key)?.id ?? null,
    key: c.key,
    old_value: c.from,
    new_value: c.to,
    changed_at: changedAt,
  }))
  return {
    stored_id: newId('store'),
    written: written.length,
    created_facts: created,
    history,
    trace_id: traceId(),
  }
}

export const mockCaptureApi: CaptureApi = {
  async extract(body, signal) {
    const { scope, text, truncated, docId } = readInput(body)
    // One full extraction: about as long as a preview plus a store.
    await delay(1800 + Math.min(text.length / 20, 1500), signal)
    const { facts, corrections } = extract(text)
    const written = facts.flatMap((f) =>
      f.entity ? [{ entity: f.entity, key: f.key, value: f.value }] : [],
    )
    return {
      ...save(scope, written, corrections),
      scope,
      doc_id: docId,
      truncated,
      truncated_reason: truncated ? TRUNCATED_REASON : null,
    }
  },

  async preview(body, signal) {
    const { scope, text, source, truncated, docId } = readInput(body)

    // Agent Memory's preview takes a few seconds per call.
    await delay(1200 + Math.min(text.length / 20, 1500), signal)

    const { facts, corrections } = extract(text)
    const triples = new Map<string, { entity: string; key: string; value: string }>()
    const unlinked = new Map<string, { key: string; value: string }>()
    const entities = [
      ...new Set(facts.map((f) => f.entity).filter((e): e is string => e !== null)),
    ]
    const extracted: ExtractedFact[] = facts.map((f, i) => {
      const id = `e${i + 1}`
      if (f.entity) triples.set(id, { entity: f.entity, key: f.key, value: f.value })
      else unlinked.set(id, { key: f.key, value: f.value })
      return {
        id,
        fact: f.fact,
        type: f.type,
        source,
        note: f.note,
        storable: f.entity !== null,
        needs_entity: f.entity === null && entities.length > 0,
      }
    })

    const response: CapturePreviewResponse = {
      preview_id: newId('prev'),
      scope,
      extracted,
      stats: {
        total: extracted.length,
        uncertain: extracted.filter((f) => (f.note ?? '').startsWith('uncertain')).length,
        corrections: corrections.length,
      },
      truncated,
      truncated_reason: truncated ? TRUNCATED_REASON : null,
      doc_id: docId,
      corrections: corrections.map((c) => JSON.stringify(c)),
      entities: entities.map((name) => ({ name, entity_type: 'thing' })),
      trace_id: traceId(),
    }
    previews.set(response.preview_id, {
      response,
      text,
      triples,
      unlinked,
      entities,
      corrections,
    })
    while (previews.size > MAX_PREVIEWS)
      previews.delete(previews.keys().next().value as string)
    return response
  },

  async store(body, signal) {
    currentUser()
    const stored = previews.get(body.preview_id)
    if (!stored)
      throw new ApiError(404, 'Preview not found or expired; run preview again.')
    if (body.scope != null && body.scope !== stored.response.scope) {
      throw new ApiError(403, 'This preview was for another scope.')
    }
    // Re-checked at store time, as the backend does: a grant may have been revoked.
    writeScope(stored.response.scope)
    const known = new Set(stored.response.extracted.map((f) => f.id))
    const unknown = body.kept.filter((id) => !known.has(id))
    if (unknown.length) {
      throw new ApiError(422, `Unknown fact ids for this preview: ${unknown.join(', ')}`)
    }

    let written: { entity: string; key: string; value: string }[]
    if (body.config.mode === 'full') {
      // Full re-extraction stores everything, kept or not.
      written = [...stored.triples.values()]
    } else {
      const choices = body.entity_choices ?? {}
      for (const [id, entity] of Object.entries(choices)) {
        if (!stored.unlinked.has(id)) {
          throw new ApiError(422, `Fact ${id} does not need an entity choice`)
        }
        if (!stored.entities.includes(entity)) {
          throw new ApiError(422, `'${entity}' is not an entity found in this preview`)
        }
      }
      written = body.kept.flatMap((id) => {
        const triple = stored.triples.get(id)
        if (triple) return [triple]
        const fact = stored.unlinked.get(id)
        const entity = choices[id]
        return fact && entity ? [{ entity, key: fact.key, value: fact.value }] : []
      })
      if (!written.length) {
        throw new ApiError(
          422,
          'None of the kept facts can be stored as triples; use mode full.',
        )
      }
    }

    await delay(900 + written.length * 150, signal)
    return save(stored.response.scope, written, stored.corrections)
  },

  async documentStatus(docId, signal) {
    currentUser()
    await delay(200, signal)
    const doc = documents.get(docId)
    if (!doc) throw new ApiError(404, 'Document not found.')
    const elapsed = Date.now() - doc.uploadedAt
    const status = elapsed < 3000 ? 'queued' : elapsed < 8000 ? 'processing' : 'ready'
    const ready = status === 'ready'
    const stamp = (ms: number) => new Date(ms).toISOString().replace(/\.\d+Z$/, '+00:00')
    return {
      doc_id: docId,
      status,
      finished: ready,
      chunks: ready ? Math.max(1, Math.ceil(doc.words / 300)) : 0,
      keywords: ready ? Math.max(3, Math.ceil(doc.words / 60)) : 0,
      created_at: stamp(doc.uploadedAt),
      updated_at: stamp(Date.now()),
      message: {
        queued: 'Waiting in Agent Memory queue...',
        processing: 'Agent Memory is chunking and indexing the document...',
        ready: 'Processed: passages are searchable.',
      }[status],
    }
  },
}
