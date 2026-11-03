import type { EntityChoice, ExtractedFact, StoreMode } from '@/api/capture'
import { uncertaintyReason } from '@/components/capture/format'
import { canKeep, factWithEntity, type EntityChoices } from '@/components/capture/keep'

interface Props {
  facts: ExtractedFact[]
  mode: StoreMode
  kept: ReadonlySet<string>
  onToggle: (id: string) => void
  /** Entities the preview found, offered for facts with no entity link. */
  entities?: EntityChoice[]
  choices?: EntityChoices
  onChoose?: (id: string, entity: string) => void
  disabled?: boolean
}

export default function FactTable({
  facts,
  mode,
  kept,
  onToggle,
  entities = [],
  choices = {},
  onChoose,
  disabled,
}: Props) {
  if (!facts.length) {
    return <p className="empty">Agent Memory found no facts in this input.</p>
  }
  return (
    <table className="capture-table capture-facts">
      <caption className="visually-hidden">Extracted facts</caption>
      <thead>
        <tr>
          <th scope="col">Keep</th>
          <th scope="col">Fact</th>
          <th scope="col">Type</th>
          <th scope="col">Source</th>
          <th scope="col">Note</th>
        </tr>
      </thead>
      <tbody>
        {facts.map((fact) => {
          const allowed = canKeep(fact, mode, choices)
          const picking = fact.needs_entity && mode === 'triples' && entities.length > 0
          const checked = allowed && kept.has(fact.id)
          return (
            <tr key={fact.id} data-kept={checked}>
              <td data-label="Keep">
                <label className="capture-check">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!allowed || disabled}
                    onChange={() => onToggle(fact.id)}
                    aria-label={`Keep ${fact.fact}`}
                  />
                </label>
              </td>
              <td data-label="Fact">
                <span className="mono capture-fact">{factWithEntity(fact, choices)}</span>
                {picking && (
                  <label className="capture-entity">
                    <span>Belongs to</span>
                    <select
                      value={choices[fact.id] ?? ''}
                      disabled={disabled}
                      onChange={(event) => onChoose?.(fact.id, event.target.value)}
                      aria-label={'Entity for ' + fact.fact}
                    >
                      <option value="">Pick an entity…</option>
                      {entities.map((entity) => (
                        <option key={entity.name} value={entity.name}>
                          {entity.name} ({entity.entity_type})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </td>
              <td data-label="Type">
                <span className="tag">{fact.type}</span>
              </td>
              <td data-label="Source" className="capture-muted">
                {fact.source}
              </td>
              <td data-label="Note">
                <FactNote fact={fact} mode={mode} picked={Boolean(choices[fact.id])} />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function FactNote({
  fact,
  mode,
  picked,
}: {
  fact: ExtractedFact
  mode: StoreMode
  picked: boolean
}) {
  const uncertain = uncertaintyReason(fact.note)
  if (!uncertain && fact.storable) {
    return <span className="capture-muted">{fact.note ?? '—'}</span>
  }
  return (
    <span className="capture-notes">
      {uncertain && (
        <span>
          <span className="tag" data-tone="warn">
            uncertain
          </span>{' '}
          {uncertain}
        </span>
      )}
      {!fact.storable &&
        (mode === 'full' ? (
          <span title={fact.note ?? undefined}>
            No entity link in the preview; full re-extraction will store it.
          </span>
        ) : picked ? (
          <span>
            <span className="tag" data-tone="good">
              entity picked
            </span>{' '}
            Stored as a triple on the entity you chose.
          </span>
        ) : fact.needs_entity ? (
          <span title={fact.note ?? undefined}>
            <span className="tag" data-tone="note">
              pick entity
            </span>{' '}
            Agent Memory didn&apos;t say which entity this belongs to. Pick one to store
            it.
          </span>
        ) : (
          <span title={fact.note ?? undefined}>
            <span className="tag" data-tone="note">
              full only
            </span>{' '}
            No entity link in the preview, so it can only be stored with full
            re-extraction.
          </span>
        ))}
    </span>
  )
}
