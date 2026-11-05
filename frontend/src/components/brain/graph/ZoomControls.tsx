/**
 * The +/- pair beside the 2d/3d switch, as in membrain's ZoomControls.jsx. It
 * wears the switch's pill so the two read as one cluster.
 */
export default function ZoomControls({
  onZoomIn,
  onZoomOut,
  onFit,
}: {
  onZoomIn: () => void
  onZoomOut: () => void
  onFit: () => void
}) {
  const icon = (d: string) => (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  )
  return (
    <fieldset className="graph-pill">
      <legend className="visually-hidden">Zoom</legend>
      <button
        type="button"
        aria-label="Zoom in"
        className="graph-pill-btn"
        onClick={onZoomIn}
      >
        {icon('M5 12h14M12 5v14')}
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        className="graph-pill-btn"
        onClick={onZoomOut}
      >
        {icon('M5 12h14')}
      </button>
      <button
        type="button"
        aria-label="Fit to screen"
        className="graph-pill-btn"
        onClick={onFit}
      >
        {icon('M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5')}
      </button>
    </fieldset>
  )
}
