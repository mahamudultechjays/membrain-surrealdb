import { useContext, type ReactNode } from 'react'
import { HeaderSlotContext } from '@/components/headerSlotContext'
import { PageActiveContext } from '@/components/pageActiveContext'

interface Props {
  active: boolean
  children: ReactNode
}

/**
 * Keeps a view mounted while it is hidden, so leaving it and coming back keeps
 * what was typed, picked and fetched. A hidden view gives up the header slot,
 * and dialogs inside it stop trapping keys (see PageActiveContext).
 */
export default function KeepAlive({ active, children }: Props) {
  const slot = useContext(HeaderSlotContext)
  const shown = useContext(PageActiveContext) && active
  return (
    <div className="keep-alive" hidden={!active}>
      <PageActiveContext.Provider value={shown}>
        <HeaderSlotContext.Provider value={shown ? slot : null}>
          {children}
        </HeaderSlotContext.Provider>
      </PageActiveContext.Provider>
    </div>
  )
}
