// The UI calls the real backend through /api. Set VITE_USE_MOCK_API=true to run
// on the in-browser mock of the capture, ask and scope endpoints instead, e.g.
// when Agent Memory is unavailable.
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === 'true'
