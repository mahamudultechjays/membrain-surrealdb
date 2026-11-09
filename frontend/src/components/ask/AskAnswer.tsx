import type { AskFact, AskResponse } from '@/api/ask'
import type { VctApi } from '@/api/vct'
import FactRow from '@/components/ask/FactRow'

interface Props {
  answer: AskResponse
  /** Whose grants were read, e.g. "Priya" or "Priya + Arun". */
  who: string
  vctApi?: VctApi
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * One recall, two columns. Normal lists every hit in the order Agent Memory
 * ranked them; Value-driven keeps only the hits whose value chain tags match
 * the filter, in the same order. Facts match on their own tags, memory chunks
 * through the facts captured with them.
 */
export default function AskAnswer({ answer, who, vctApi }: Props) {
  const { metadata } = answer
  const filter = metadata.filter
  const valueFacts = answer.value_facts ?? null

  return (
    <section className="ask-answer" aria-labelledby="ask-answer-heading">
      <h2 id="ask-answer-heading">{answer.q}</h2>
      <p className="mono ask-summary">
        {plural(metadata.total_facts, 'result')} · {plural(answer.scopes.length, 'scope')}{' '}
        read · tier {metadata.resolution_tier ?? 'none'} ·{' '}
        {metadata.latency_ms.toLocaleString('en')} ms · as {who}
      </p>

      <div className="ask-columns">
        <Column
          title="Normal"
          note="Everything Agent Memory found, best match first."
          facts={answer.facts}
          empty={`Nothing found in ${answer.scopes.join(', ')}`}
          vctApi={vctApi}
        />
        {valueFacts === null || !filter ? (
          <section className="ask-column" aria-label="Value-driven">
            <ColumnHead title="Value-driven" />
            <p className="ask-muted ask-column-empty">
              Pick a domain, node or goal in the value-driven filter to see only the
              results tied to that part of the value chain.
            </p>
          </section>
        ) : (
          <Column
            title="Value-driven"
            note={`${[...filter.domains, ...filter.nodes, ...filter.goals].join(', ')} · ${plural(filter.removed, 'result')} left out`}
            facts={valueFacts}
            empty="None of these results is tagged with that part of the value chain."
            vctApi={vctApi}
          />
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

function ColumnHead({ title, count }: { title: string; count?: number }) {
  return (
    <header className="ask-column-head">
      <h3>{title}</h3>
      {count !== undefined && <span className="mono ask-count">{count}</span>}
    </header>
  )
}

function Column({
  title,
  note,
  facts,
  empty,
  vctApi,
}: {
  title: string
  note: string
  facts: AskFact[]
  empty: string
  vctApi?: VctApi
}) {
  return (
    <section className="ask-column" aria-label={title}>
      <ColumnHead title={title} count={facts.length} />
      <p className="mono ask-muted ask-column-note">{note}</p>
      <div className="ask-results">
        {facts.length === 0 ? (
          <p className="ask-muted">{empty}</p>
        ) : (
          <ul className="ask-facts" aria-label={`${title} results`}>
            {facts.map((fact) => (
              <FactRow key={fact.source.hit_id} fact={fact} vctApi={vctApi} />
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
