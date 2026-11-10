import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import { mockPromotionApi, resetMockPromotion } from '@/api/mock/promotion'
import type { PromotionApi } from '@/api/promotion'
import PromotionPanel from '@/components/admin/PromotionPanel'
import AdminPage from '@/pages/AdminPage'

function spyApi(overrides: Partial<PromotionApi> = {}): PromotionApi {
  return {
    status: vi.fn<PromotionApi['status']>(mockPromotionApi.status),
    run: vi.fn<PromotionApi['run']>(mockPromotionApi.run),
    approve: vi.fn<PromotionApi['approve']>(mockPromotionApi.approve),
    reject: vi.fn<PromotionApi['reject']>(mockPromotionApi.reject),
    keep: vi.fn<PromotionApi['keep']>(mockPromotionApi.keep),
    close: vi.fn<PromotionApi['close']>(mockPromotionApi.close),
    ...overrides,
  }
}

const card = () =>
  screen.getByRole('article', { name: 'Cobalt Ridge return window = 30 days' })

describe('PromotionPanel', () => {
  beforeEach(() => {
    resetMockPromotion()
    window.location.hash = ''
  })

  it('shows the status bar, the filters with counts and the side column', async () => {
    render(<PromotionPanel api={spyApi()} />)
    expect(await screen.findByText('org/spreetail/team/common')).toBeInTheDocument()
    expect(screen.getByText(/14 new statements, 14 grouped/)).toBeInTheDocument()
    expect(screen.getByText(/manual only/)).toBeInTheDocument()
    const filters = screen.getByRole('group', { name: 'Show' })
    expect(
      within(filters)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Candidates · 2', 'Flags · 1', 'Decided · 2', 'All groups · 4'])
    const flag = screen.getByRole('region', { name: 'Differs from a team rule' })
    expect(
      within(flag).getByText(/Northwind free freight threshold = \$5,000/),
    ).toBeInTheDocument()
    expect(within(flag).getByText(/Member F said/)).toBeInTheDocument()
    const decided = screen.getByRole('region', { name: 'Recently decided' })
    expect(
      within(decided).getByText('Reno warehouse closing time = 6 pm'),
    ).toBeInTheDocument()
    const settings = screen.getByRole('region', { name: 'Settings in use' })
    expect(within(settings).getByText('candidate at')).toBeInTheDocument()
  })

  it('opens the top candidate with its values, score and who said what', async () => {
    render(<PromotionPanel api={spyApi()} />)
    await screen.findByText('org/spreetail/team/common')
    const top = card()
    expect(within(top).getByText('3.5')).toBeInTheDocument()
    expect(within(top).getByText('team score · threshold 3')).toBeInTheDocument()
    expect(within(top).getByText('30 days · 3.5')).toBeInTheDocument()
    expect(within(top).getByText('60 days · 1')).toBeInTheDocument()
    expect(within(top).getByText('For · 4.5')).toBeInTheDocument()
    expect(within(top).getByText('Against · 1')).toBeInTheDocument()
    const memberA = within(top).getByRole('row', { name: /Member A/ })
    expect(within(memberA).getByText('1 + 0.5')).toBeInTheDocument()
    expect(
      within(memberA).getByText('“Cobalt Ridge returns are 30 days”'),
    ).toBeInTheDocument()
    expect(within(memberA).getByText(/capture · 3 Nov, 9 Nov/)).toBeInTheDocument()
    // The second candidate stays collapsed until its arrow is clicked.
    const folded = () =>
      screen.getByRole('article', { name: 'Northwind lead time = 21 days' })
    const arrow = within(folded()).getByRole('button', { name: 'Expand' })
    expect(arrow).toHaveAttribute('aria-expanded', 'false')
    expect(
      within(folded()).queryByRole('button', { name: 'Approve as team rule' }),
    ).not.toBeInTheDocument()
    fireEvent.click(arrow)
    expect(within(folded()).getByRole('button', { name: 'Collapse' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(
      within(folded()).getByRole('button', { name: 'Approve as team rule' }),
    ).toBeInTheDocument()
    // Both stay open; the top one collapses with its own arrow.
    fireEvent.click(within(top).getByRole('button', { name: 'Collapse' }))
    expect(
      within(top).queryByRole('button', { name: 'Approve as team rule' }),
    ).not.toBeInTheDocument()
  })

  it('approves with the edited wording, entity and key', async () => {
    const api = spyApi()
    render(<PromotionPanel api={api} />)
    await screen.findByText('org/spreetail/team/common')
    fireEvent.click(within(card()).getByRole('button', { name: 'Approve as team rule' }))
    fireEvent.change(within(card()).getByLabelText('Key'), {
      target: { value: 'returns_window' },
    })
    fireEvent.change(within(card()).getByLabelText('Value'), {
      target: { value: '30 calendar days' },
    })
    fireEvent.click(within(card()).getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(api.approve).toHaveBeenCalledWith(1, {
        label: 'Cobalt Ridge return window',
        entity_type: 'organization',
        entity: 'Cobalt Ridge',
        key: 'returns_window',
        value: '30 calendar days',
      }),
    )
  })

  it('rejects a candidate', async () => {
    const api = spyApi()
    render(<PromotionPanel api={api} />)
    await screen.findByText('org/spreetail/team/common')
    fireEvent.click(within(card()).getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(api.reject).toHaveBeenCalledWith(1))
  })

  it('lists flags under Flags, once, and in the side column elsewhere', async () => {
    const api = spyApi()
    render(<PromotionPanel api={api} />)
    await screen.findByText('org/spreetail/team/common')
    fireEvent.click(screen.getByRole('button', { name: 'Decided · 2' }))
    expect(
      screen.getAllByRole('region', { name: 'Differs from a team rule' }),
    ).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Flags · 1' }))
    const [flag, ...more] = screen.getAllByRole('region', {
      name: 'Differs from a team rule',
    })
    expect(more).toHaveLength(0)
    fireEvent.click(
      within(flag as HTMLElement).getByRole('button', { name: 'Close rule' }),
    )
    await waitFor(() => expect(api.close).toHaveBeenCalledWith(3))
  })

  it('keeps a rule from its flag', async () => {
    const api = spyApi()
    render(<PromotionPanel api={api} />)
    const flag = await screen.findByRole('region', { name: 'Differs from a team rule' })
    fireEvent.click(within(flag).getByRole('button', { name: 'Keep rule' }))
    await waitFor(() => expect(api.keep).toHaveBeenCalledWith(3))
  })

  it('closes an active rule from Decided', async () => {
    const api = spyApi()
    render(<PromotionPanel api={api} />)
    await screen.findByText('org/spreetail/team/common')
    fireEvent.click(screen.getByRole('button', { name: 'Decided · 2' }))
    const rule = screen.getByRole('article', {
      name: 'Northwind free freight threshold = $5,000',
    })
    fireEvent.click(within(rule).getByRole('button', { name: 'Close rule' }))
    await waitFor(() => expect(api.close).toHaveBeenCalledWith(2))
  })

  it('lists every topic under All groups', async () => {
    render(<PromotionPanel api={spyApi()} />)
    await screen.findByText('org/spreetail/team/common')
    fireEvent.click(screen.getByRole('button', { name: 'All groups · 4' }))
    expect(
      screen.getByRole('article', { name: 'Reno warehouse closing time' }),
    ).toBeInTheDocument()
  })

  it('says when a run is already going', async () => {
    const api = spyApi({
      run: vi.fn<PromotionApi['run']>(() =>
        Promise.reject(new ApiError(409, 'Promotion is already running.')),
      ),
    })
    render(<PromotionPanel api={api} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run now' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Promotion is already running.',
    )
  })
})

describe('AdminPage tabs', () => {
  const base: Me = { email: 'p@x.com', name: 'P', is_admin: false, grants: [] }

  it('shows a team admin only the Promotion tab', async () => {
    window.location.hash = '#/admin'
    render(<AdminPage me={{ ...base, is_team_admin: true }} promotionApi={spyApi()} />)
    const tabs = screen.getByRole('navigation', { name: 'Admin section' })
    expect(
      within(tabs)
        .getAllByRole('link')
        .map((a) => a.textContent),
    ).toEqual(['Promotion'])
    expect(await screen.findByText('org/spreetail/team/common')).toBeInTheDocument()
  })

  it('shows an org admin all four tabs', () => {
    window.location.hash = '#/admin'
    render(<AdminPage me={{ ...base, is_admin: true }} promotionApi={spyApi()} />)
    const tabs = screen.getByRole('navigation', { name: 'Admin section' })
    expect(
      within(tabs)
        .getAllByRole('link')
        .map((a) => a.textContent),
    ).toEqual(['Access', 'Lab', 'Value chain', 'Promotion'])
  })
})
