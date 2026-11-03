import { fireEvent, render, screen } from '@testing-library/react'
import type { Me } from '@/api/auth'
import Account from '@/components/Account'

const ME: Me = {
  email: 'arun.das@spreetail.com',
  name: 'Arun Das',
  is_admin: true,
  grants: [],
}

describe('Account', () => {
  it('shows the initial, then who is signed in, the theme switch and sign out', () => {
    const onToggleTheme = vi.fn<() => void>()
    const onSignOut = vi.fn<() => void>()
    render(
      <Account
        me={ME}
        dark={false}
        onToggleTheme={onToggleTheme}
        onSignOut={onSignOut}
      />,
    )

    const avatar = screen.getByRole('button', { name: 'Account: Arun Das' })
    expect(avatar).toHaveTextContent('A')
    expect(screen.queryByText(ME.email)).not.toBeInTheDocument()

    fireEvent.click(avatar)
    expect(screen.getByText(ME.email)).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    const theme = screen.getByRole('switch', { name: 'Dark theme' })
    expect(theme).not.toBeChecked()

    fireEvent.click(theme)
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(onToggleTheme).toHaveBeenCalledOnce()
    expect(onSignOut).toHaveBeenCalledOnce()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText(ME.email)).not.toBeInTheDocument()
    expect(avatar).toHaveFocus()
  })
})
