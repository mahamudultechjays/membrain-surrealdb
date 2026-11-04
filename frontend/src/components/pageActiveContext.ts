import { createContext } from 'react'

/**
 * False while the view around a component is kept mounted but hidden (see
 * KeepAlive), so things with page-wide effects, like a dialog's key trap and
 * scroll lock, can stand down. True outside any KeepAlive.
 */
export const PageActiveContext = createContext(true)
