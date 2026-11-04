import type { MemoryCategory, StoreMode } from '@/api/capture'

const MODES: { mode: StoreMode; label: string; detail: string }[] = [
  {
    mode: 'triples',
    label: 'Only the facts I keep (triples)',
    detail: 'Writes exactly the rows you tick, so what is stored matches the preview.',
  },
  {
    mode: 'full',
    label: 'Re-extract everything (full)',
    detail:
      'No preview: Agent Memory reads the input and stores all it finds, including facts with no entity link.',
  },
]

const CATEGORIES: { value: MemoryCategory | null; label: string }[] = [
  { value: null, label: 'As extracted' },
  { value: 'identity', label: 'Identity' },
  { value: 'knowledge', label: 'Knowledge' },
  { value: 'context', label: 'Context' },
]

interface Props {
  mode: StoreMode
  onModeChange: (mode: StoreMode) => void
  category: MemoryCategory | null
  onCategoryChange: (category: MemoryCategory | null) => void
}

export default function CaptureSettings({
  mode,
  onModeChange,
  category,
  onCategoryChange,
}: Props) {
  return (
    <div className="capture-settings">
      <fieldset className="capture-modes">
        <legend>How to store</legend>
        {MODES.map((option) => (
          <label
            key={option.mode}
            className="capture-radio"
            data-checked={mode === option.mode}
          >
            <input
              type="radio"
              name="capture-mode"
              value={option.mode}
              checked={mode === option.mode}
              onChange={() => onModeChange(option.mode)}
            />
            <span className="capture-radio-label">{option.label}</span>
            <span className="capture-radio-detail">{option.detail}</span>
          </label>
        ))}
      </fieldset>
      <div className="capture-field">
        <label htmlFor="capture-category">Memory category</label>
        <select
          id="capture-category"
          value={category ?? ''}
          // Full re-extraction lets Agent Memory pick categories; the backend ignores this then.
          disabled={mode === 'full'}
          onChange={(e) =>
            onCategoryChange((e.target.value || null) as MemoryCategory | null)
          }
          aria-describedby="capture-category-hint"
        >
          {CATEGORIES.map((option) => (
            <option key={option.label} value={option.value ?? ''}>
              {option.label}
            </option>
          ))}
        </select>
        <span id="capture-category-hint" className="capture-hint">
          {mode === 'full'
            ? 'Full re-extraction keeps the categories Agent Memory chooses.'
            : category
              ? `Every kept fact is stored as ${category}, whatever Agent Memory gave it. A fact already in memory with the same value keeps its old category.`
              : 'Each fact keeps the category Agent Memory gave it. Pick one to store every kept fact with that category instead.'}
        </span>
      </div>
    </div>
  )
}
