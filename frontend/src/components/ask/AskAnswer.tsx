import type { AskLayer, AskResponse } from '@/api/ask'
import type { VctApi } from '@/api/vct'
import { findConflicts } from '@/components/ask/conflicts'
import FactRow from '@/components/ask/FactRow'
import { LAYER_LABELS } from '@/components/ask/layers'

interface Props {
  answer: AskResponse
  /** Whose grants were read, e.g. "Priya" or "Priya + Arun". */
  who: string
  /** Also list, crossed out, the facts the VCT filter dropped. */
  compare?: boolean
  vctApi?: VctApi
}

/** The answer, one section per layer in the order the backend returned them. */
export default function AskAnswer({ answer, who, compare = false, vctApi }: Props) {
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
      {metadata.filter && (
        <p className="mono ask-summary">
          value chain filter{' '}
          {[
            ...metadata.filter.goals,
            ...metadata.filter.nodes,
            ...metadata.filter.domains,
          ].join(', ')}{' '}
          · {plural(metadata.filter.removed, 'result')} removed
        </p>
      )}

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
        <LayerSection
          key={`${layer.layer}:${layer.area}`}
          layer={layer}
          compare={compare}
          vctApi={vctApi}
        />
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

function LayerSection({
  layer,
  compare,
  vctApi,
}: {
  layer: AskLayer
  compare: boolean
  vctApi?: VctApi
}) {
  const removed = compare ? (layer.removed ?? []) : []
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
            <FactRow key={fact.source.hit_id} fact={fact} vctApi={vctApi} />
          ))}
        </ul>
      )}
      {removed.length > 0 && (
        <div className="vct-removed">
          <p className="ask-muted">Removed by the filter ({removed.length})</p>
          <ul className="ask-facts">
            {removed.map((fact) => (
              <FactRow key={fact.source.hit_id} fact={fact} removed />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
