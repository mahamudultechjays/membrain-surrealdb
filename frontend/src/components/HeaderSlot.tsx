import { useContext, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { HeaderSlotContext } from '@/components/headerSlotContext'

/** Renders its children in the header's right-hand slot (see headerSlotContext). */
export default function HeaderSlot({ children }: { children: ReactNode }) {
  const slot = useContext(HeaderSlotContext)
  if (slot === undefined) return <>{children}</>
  return slot ? createPortal(children, slot) : null
}
