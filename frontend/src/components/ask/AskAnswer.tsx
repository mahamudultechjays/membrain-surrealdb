import type { AskResponse } from '@/api/ask'
import FactRow from '@/components/ask/FactRow'

interface Props {
  answer: AskResponse
  /** Whose grants were read, e.g. "Priya" or "Priya + Arun". */
  who: string
}

/** The answer: one list, in the order Agent Memory ranked it across every scope read. */
export default function AskAnswer({ answer, who }: Props) {
  const { metadata } = answer
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

  return (
    <section className="ask-answer" aria-labelledby="ask-answer-heading">
      <h2 id="ask-answer-heading">{answer.q}</h2>
      <p className="mono ask-summary">
        {plural(metadata.total_facts, 'fact')} · {plural(answer.scopes.length, 'scope')}{' '}
        read · tier {metadata.resolution_tier ?? 'none'} ·{' '}
        {metadata.latency_ms.toLocaleString('en')} ms · as {who}
      </p>

      <div className="ask-results">
        {answer.facts.length === 0 ? (
          <p className="ask-muted">Nothing found in {answer.scopes.join(', ')}</p>
        ) : (
          <ul className="ask-facts" aria-label="Results">
            {answer.facts.map((fact) => (
              <FactRow key={fact.source.hit_id} fact={fact} />
            ))}
          </ul>
        )}
      </div>

      <footer className="mono ask-footer">
        <span>trace {answer.trace_id ?? 'none'}</span>
        {metadata.trace_ids.length > 0 && (
          <span>memory trace {metadata.trace_ids.join(', ')}</span>
        )}
        <span>answered {answer.answered_at}</span>
      </footer>
    </section>
  )
}
