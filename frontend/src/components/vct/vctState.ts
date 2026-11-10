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
