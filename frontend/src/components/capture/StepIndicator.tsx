export type CaptureStep = 'input' | 'preview' | 'stored'

const STEPS: { step: CaptureStep; label: string }[] = [
  { step: 'input', label: 'Input' },
  { step: 'preview', label: 'Preview' },
  { step: 'stored', label: 'Stored' },
]

export default function StepIndicator({ current }: { current: CaptureStep }) {
  const currentIndex = STEPS.findIndex((s) => s.step === current)
  return (
    <ol className="capture-steps" aria-label="Capture progress">
      {STEPS.map(({ step, label }, index) => (
        <li
          key={step}
          data-state={
            index === currentIndex ? 'current' : index < currentIndex ? 'done' : 'todo'
          }
          aria-current={index === currentIndex ? 'step' : undefined}
        >
          <span className="capture-step-num">{index + 1}</span> {label}
        </li>
      ))}
    </ol>
  )
}
