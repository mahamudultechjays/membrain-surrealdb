import type { AskLayer, AskResponse } from '@/api/ask'
import { findConflicts } from '@/components/ask/conflicts'
import FactRow from '@/components/ask/FactRow'
import { LAYER_LABELS } from '@/components/ask/layers'

interface Props {
  answer: AskResponse
  /** Whose grants were read, e.g. "Priya" or "Priya + Arun". */
  who: string
}

/** The answer, one section per layer in the order the backend returned them. */
export default function AskAnswer({ answer, who }: Props) {
  const { metadata } = answer
  const conflicts = findConflicts(answer.layers)
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

  return (
    <section className="ask-answer" aria-labelledby="ask-answer-heading">
      <h2 id="ask-answer-heading">{answer.q}</h2>
      <p className="mono ask-summary">
        {plural(metadata.total_facts, 'fact')} · {plural(answer.layers.length, 'layer')}{' '}
        read · tier {metadata.resolution_tier ?? 'none'} ·{' '}
        {metadata.latency_ms.toLocaleString('en')} ms · as {who}
      </p>

      {conflicts.map((conflict) => (
        <div key={conflict.entity} className="ask-conflict" role="note">
          <strong>Layers disagree on {conflict.entity}.</strong>{' '}
          {conflict.values.map((v, i) => (
            <span key={v.value}>
              {i > 0 && ' · '}
              <span className="mono">{v.value}</span> ({v.layers.join(', ')})
            </span>
          ))}
          . Nothing decides between them yet; check the sources.
        </div>
      ))}

      {answer.layers.map((layer) => (
        <LayerSection key={`${layer.layer}:${layer.area}`} layer={layer} />
      ))}

      <footer className="mono ask-footer">
        <span>trace {answer.trace_id ?? 'none'}</span>
        {metadata.trace_ids.length > 0 && (
          <span>layer traces {metadata.trace_ids.join(', ')}</span>
        )}
        <span>answered {answer.answered_at}</span>
      </footer>
    </section>
  )
}

function LayerSection({ layer }: { layer: AskLayer }) {
  return (
    <section
      className="ask-layer"
      aria-label={`${LAYER_LABELS[layer.layer]} ${layer.area}`}
    >
      <header className="ask-layer-head">
        <h3>
          {LAYER_LABELS[layer.layer]} <span className="mono ask-area">{layer.area}</span>
          {layer.layer === 'personal' && layer.owner && (
            <span className="ask-owner"> · {layer.owner}</span>
          )}
        </h3>
        <span className="mono ask-count">{layer.facts.length}</span>
      </header>
      {/* One layer failing still lets the others answer. */}
      {layer.error ? (
        <p className="error">Recall failed for this layer: {layer.error}</p>
      ) : layer.facts.length === 0 ? (
        <p className="ask-muted">Nothing found in {layer.area}</p>
      ) : (
        <ul className="ask-facts">
          {layer.facts.map((fact) => (
            <FactRow key={fact.source.hit_id} fact={fact} />
          ))}
        </ul>
      )}
    </section>
  )
}
