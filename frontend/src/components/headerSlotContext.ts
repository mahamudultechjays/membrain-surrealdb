import { createContext } from 'react'

/**
 * The header's right-hand slot, where a page puts its own controls (the person
 * dropdown). undefined: no App around the page (tests), so render in place.
 * null: App is mounting and the slot isn't in the DOM yet.
 */
export const HeaderSlotContext = createContext<HTMLElement | null | undefined>(undefined)
