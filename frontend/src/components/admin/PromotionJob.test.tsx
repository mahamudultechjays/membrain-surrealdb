import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { mockPromotionApi } from '@/api/mock/promotion'
import type { PromotionApi, PromotionStatus } from '@/api/promotion'
import PromotionJob from '@/components/admin/PromotionJob'

function api(overrides: Partial<PromotionApi> = {}): PromotionApi {
  return {
    ...mockPromotionApi,
    status: vi.fn<PromotionApi['status']>(mockPromotionApi.status),
    run: vi.fn<PromotionApi['run']>(() => Promise.resolve()),
    ...overrides,
  }
}

describe('PromotionJob', () => {
  it('runs the promotion job and shows what the run found', async () => {
    const fake = api()
    render(<PromotionJob api={fake} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run promotion' }))
    await waitFor(() => expect(fake.run).toHaveBeenCalledTimes(1))
    expect(
      await screen.findByText(/42 facts listed, 14 new, 14 grouped/),
    ).toBeInTheDocument()
    expect(screen.getByText(/3 open for review/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review in Promotion' })).toHaveAttribute(
      'href',
      '#/admin/promotion',
    )
  })

  it('says when a run is already going', async () => {
    const fake = api({
      run: vi.fn<PromotionApi['run']>(() =>
        Promise.reject(new ApiError(409, 'Promotion is already running.')),
      ),
    })
    render(<PromotionJob api={fake} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run promotion' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Promotion is already running.',
    )
  })

  it('warns when the grouping model has no key', async () => {
    const status = await mockPromotionApi.status()
    const fake = api({
      status: vi.fn<PromotionApi['status']>(() =>
        Promise.resolve<PromotionStatus>({ ...status, model_configured: false }),
      ),
    })
    render(<PromotionJob api={fake} />)
    expect(await screen.findByText(/ANTHROPIC_API_KEY is not set/)).toBeInTheDocument()
  })
})
