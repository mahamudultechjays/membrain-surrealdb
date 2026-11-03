import { useState, type ChangeEvent } from 'react'
import { LARGE_DOCUMENT_WORDS, MAX_FILE_BYTES, MAX_TEXT_CHARS } from '@/api/capture'
import { formatBytes, formatCount } from '@/components/capture/format'

export type InputTab = 'text' | 'document'

/** Exercises every preview state in the mock: a correction, a hedge, and a pronoun with no entity. */
export const SAMPLE_TEXT =
  "Acme Logistics ships to our Reno warehouse. Acme's lead time is 18 days, up from 10. I think the returns window is 60 days now. Dock 3 is closed this week. It is late again."

const ACCEPTED = /\.(pdf|txt|md)$/i

interface Props {
  tab: InputTab
  onTabChange: (tab: InputTab) => void
  text: string
  onTextChange: (text: string) => void
  file: File | null
  onFileChange: (file: File | null) => void
}

export default function CaptureInput({
  tab,
  onTabChange,
  text,
  onTextChange,
  file,
  onFileChange,
}: Props) {
  return (
    <div className="capture-input">
      <div className="capture-tabs" role="tablist" aria-label="Input type">
        {(['text', 'document'] as const).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            id={`capture-tab-${name}`}
            aria-selected={tab === name}
            aria-controls={`capture-panel-${name}`}
            onClick={() => onTabChange(name)}
          >
            {name === 'text' ? 'Text' : 'Document'}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`capture-panel-${tab}`}
        aria-labelledby={`capture-tab-${tab}`}
      >
        {tab === 'text' ? (
          <TextInput text={text} onChange={onTextChange} />
        ) : (
          <DocumentInput file={file} onChange={onFileChange} />
        )}
      </div>
    </div>
  )
}

function TextInput({ text, onChange }: { text: string; onChange: (t: string) => void }) {
  const over = text.length - MAX_TEXT_CHARS
  return (
    <div className="capture-field">
      <label htmlFor="capture-text">What do you want to remember?</label>
      <textarea
        id="capture-text"
        rows={8}
        value={text}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby="capture-text-count"
        aria-invalid={over > 0}
        placeholder="Paste notes, an email or a chat message."
      />
      <div className="capture-row">
        <span id="capture-text-count" className="mono capture-count" data-over={over > 0}>
          {formatCount(text.length)} / {formatCount(MAX_TEXT_CHARS)} characters
        </span>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => onChange(SAMPLE_TEXT)}
        >
          Use sample text
        </button>
      </div>
      {over > 0 && (
        <p className="error" role="alert">
          {formatCount(over)} characters over the limit. Use the Document tab for longer
          text.
        </p>
      )}
    </div>
  )
}

function DocumentInput({
  file,
  onChange,
}: {
  file: File | null
  onChange: (file: File | null) => void
}) {
  const [problem, setProblem] = useState<string | null>(null)

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = event.target.files?.[0] ?? null
    // Check here so a too-big file never gets read into memory or sent.
    if (picked && picked.size > MAX_FILE_BYTES) {
      setProblem(
        `${picked.name} is ${formatBytes(picked.size)}; files are limited to ${formatBytes(MAX_FILE_BYTES)}.`,
      )
      event.target.value = ''
      return onChange(null)
    }
    if (picked && !ACCEPTED.test(picked.name)) {
      setProblem(`${picked.name} is not a PDF, .txt or .md file.`)
      event.target.value = ''
      return onChange(null)
    }
    setProblem(null)
    onChange(picked)
  }

  return (
    <div className="capture-field">
      <p className="note">
        Agent Memory has no dry run for files, so Preview uploads the document and it
        starts processing straight away. Documents over{' '}
        {formatCount(LARGE_DOCUMENT_WORDS)} words are previewed from their first 500
        words.
      </p>
      <label htmlFor="capture-file">File (PDF, .txt or .md, up to 10 MB)</label>
      <input id="capture-file" type="file" accept=".pdf,.txt,.md" onChange={pick} />
      {file && (
        <p className="capture-file-meta">
          <span className="mono">{file.name}</span> · {formatBytes(file.size)}
        </p>
      )}
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
    </div>
  )
}
