import { useEffect, useState } from 'react'
import { vctApi, type OnboardingStatus, type VctApi, type VctMap } from '@/api/vct'

/** Shared VCT state for the components in Vct.tsx: the map, and Ask's filter value. */

// One request per API object: the map never changes while the page is open.
let mapRequests = new WeakMap<VctApi, Promise<VctMap>>()

function loadMap(api: VctApi): Promise<VctMap> {
  let request = mapRequests.get(api)
  if (!request) {
    request = api.map().catch((error: unknown) => {
      mapRequests.delete(api)
      throw error
    })
    mapRequests.set(api, request)
  }
  return request
}

/** The metro map, fetched once per page load and shared by every component. */
export function useVctMap(api: VctApi = vctApi): VctMap | null {
  const [map, setMap] = useState<VctMap | null>(null)
  useEffect(() => {
    let live = true
    loadMap(api)
      .then((m) => {
        if (live) setMap(m)
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [api])
  return map
}

/** Test hook: forget the cached maps. */
export function resetVctMapCache(): void {
  mapRequests = new WeakMap()
}

export interface VctFilterValue {
  goals: string[]
  nodes: string[]
  domains: string[]
}

export const NO_VCT_FILTER: VctFilterValue = { goals: [], nodes: [], domains: [] }

export const hasVctFilter = (value: VctFilterValue) =>
  value.goals.length + value.nodes.length + value.domains.length > 0

/**
 * The value-driven column's starting filter: the user's onboarded domains.
 * Their nodes sit inside those domains, so adding the nodes too would only
 * narrow it to the nodes; "Only my nodes" in the filter bar does that.
 */
export function filterFromOnboarding(
  status: Pick<OnboardingStatus, 'domains'> | null,
): VctFilterValue {
  return { ...NO_VCT_FILTER, domains: (status?.domains ?? []).map((d) => d.id) }
}

/** How long new tags stay in review, in hours. */
export const REVIEW_HOURS = 48

export interface ReviewTimes {
  taggedAt: string | null | undefined
  reviewedAt: string | null | undefined
}

/** Facts tagged in the last REVIEW_HOURS that nobody has reviewed yet. */
export function inReview<T extends ReviewTimes>(facts: T[], now = Date.now()): T[] {
  return facts.filter((f) => {
    if (!f.taggedAt || f.reviewedAt) return false
    const age = now - Date.parse(f.taggedAt)
    return age >= 0 && age < REVIEW_HOURS * 3600_000
  })
}

/** "1 day 21 h", "6 h", "under 1 h" left in review. */
export function timeLeft(taggedAt: string, now = Date.now()): string {
  const hours = Math.floor(
    (Date.parse(taggedAt) + REVIEW_HOURS * 3600_000 - now) / 3600_000,
  )
  if (hours < 1) return 'under 1 h'
  const days = Math.floor(hours / 24)
  const rest = hours % 24
  return days
    ? `${days} day${days > 1 ? 's' : ''}${rest ? ` ${rest} h` : ''}`
    : `${rest} h`
}
