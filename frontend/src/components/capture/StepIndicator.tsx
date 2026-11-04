export type CaptureStep = 'input' | 'preview' | 'stored'

const STEPS: { step: CaptureStep; label: string }[] = [
  { step: 'input', label: 'Input' },
  { step: 'preview', label: 'Preview' },
  { step: 'stored', label: 'Stored' },
]

interface Props {
  current: CaptureStep
  /** Re-extract everything stores straight from the input, with no preview step. */
  skipPreview?: boolean
}

export default function StepIndicator({ current, skipPreview = false }: Props) {
  const currentIndex = STEPS.findIndex((s) => s.step === current)
  return (
    <ol className="capture-steps" aria-label="Capture progress">
      {STEPS.map(({ step, label }, index) => {
        const skipped = skipPreview && step === 'preview'
        return (
          <li
            key={step}
            data-state={
              skipped
                ? 'skipped'
                : index === currentIndex
                  ? 'current'
                  : index < currentIndex
                    ? 'done'
                    : 'todo'
            }
            aria-current={index === currentIndex ? 'step' : undefined}
          >
            <span className="capture-step-num">{index + 1}</span> {label}
            {skipped && <span className="visually-hidden"> (skipped)</span>}
          </li>
        )
      })}
    </ol>
  )
}
