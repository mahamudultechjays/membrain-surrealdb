import type { FactProvenance } from '@/api/ask'
import { describeProvenance, formatScore, trustTone } from '@/components/ask/layers'

/**
 * How far Agent Memory trusts a fact, from how it was written: green for a
 * structured fact, plain for one taken from chat, amber below that. The
 * title says how it was written, how sure the writer was, and when.
 */
export default function TrustChip({ provenance }: { provenance: FactProvenance }) {
  if (provenance.trust == null) return null
  return (
    <>
      <span
        className="tag ask-trust"
        data-tone={trustTone(provenance.trust)}
        title={describeProvenance(provenance)}
      >
        trust <span className="mono">{formatScore(provenance.trust)}</span>
      </span>
      {provenance.superseded_by && (
        <span className="tag" data-tone="warn" title="A newer value replaced this one">
          Superseded
        </span>
      )}
    </>
  )
}
