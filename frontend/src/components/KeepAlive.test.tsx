import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import HeaderSlot from '@/components/HeaderSlot'
import { HeaderSlotContext } from '@/components/headerSlotContext'
import KeepAlive from '@/components/KeepAlive'
import Modal from '@/components/Modal'

function Page({ name }: { name: string }) {
  const [text, setText] = useState('')
  return (
    <main>
      <label>
        {name} notes
        <input value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <HeaderSlot>
        <span>{name} controls</span>
      </HeaderSlot>
    </main>
  )
}

function Tabs({ current, slot }: { current: 'a' | 'b'; slot: HTMLElement }) {
  return (
    <HeaderSlotContext.Provider value={slot}>
      <KeepAlive active={current === 'a'}>
        <Page name="A" />
      </KeepAlive>
      <KeepAlive active={current === 'b'}>
        <Page name="B" />
      </KeepAlive>
    </HeaderSlotContext.Provider>
  )
}

describe('KeepAlive', () => {
  it('keeps a hidden view, its typing included, and hands the header to the shown one', () => {
    const slot = document.createElement('div')
    document.body.append(slot)
    const { rerender } = render(<Tabs current="a" slot={slot} />)

    fireEvent.change(screen.getByLabelText('A notes'), { target: { value: 'draft' } })
    expect(slot).toHaveTextContent('A controls')

    rerender(<Tabs current="b" slot={slot} />)
    // Still mounted, just hidden.
    expect(screen.getByLabelText('A notes')).not.toBeVisible()
    expect(slot).toHaveTextContent('B controls')
    expect(slot).not.toHaveTextContent('A controls')

    rerender(<Tabs current="a" slot={slot} />)
    expect(screen.getByLabelText('A notes')).toHaveValue('draft')
    slot.remove()
  })

  it('lets a dialog on a hidden view stop locking scroll and catching keys', () => {
    const onClose = vi.fn<() => void>()
    const view = (active: boolean) => (
      <KeepAlive active={active}>
        <Modal title="Grant" onClose={onClose}>
          <input aria-label="Scope" />
        </Modal>
      </KeepAlive>
    )
    const { rerender } = render(view(true))
    expect(document.body.style.overflow).toBe('hidden')

    rerender(view(false))
    expect(document.body.style.overflow).toBe('')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()

    // Back on the view, the dialog is still open and takes Escape again.
    rerender(view(true))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
