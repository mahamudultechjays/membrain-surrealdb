import { useEffect, useState } from 'react'

/**
 * Seconds since this mounted. Render it only while a call runs, so each call
 * starts again from zero without resetting state from an effect.
 */
export default function ElapsedSeconds({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    )
    return () => clearInterval(timer)
  }, [])

  return (
    <output className="capture-elapsed">
      {label}… <span className="mono">{seconds} s</span>
    </output>
  )
}
