import { useEffect, useState } from 'react'
import type { Theme } from '@/hooks/useTheme'

const read = (): Theme =>
  document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'

/**
 * The theme currently on <html>, kept in sync as it changes. For things that
 * can't use the CSS tokens (a WebGL canvas) but must follow the theme switch,
 * which lives in the account menu, not in a shared context.
 */
export function useDocumentTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(read)

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(read()))
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])

  return theme
}
