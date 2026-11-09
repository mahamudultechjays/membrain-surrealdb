import { mockAdminApi } from '@/api/mock/admin'
import { mockAskApi } from '@/api/mock/ask'
import { mockAuthApi } from '@/api/mock/auth'
import { MOCK_REGISTERED, mockSession, setMockLatencyScale } from '@/api/mock/backend'
import { mockCaptureApi } from '@/api/mock/capture'

const PRIYA = 'org/user/u-0001'
const ARUN = 'org/user/u-0002'
const DEENA = 'org/user/u-0003'
const config = { mode: 'triples' as const, memory_category: null }

beforeAll(() => setMockLatencyScale(0))
afterAll(() => setMockLatencyScale(1))
// Every test starts signed in as Priya, the mock's admin.
beforeEach(() => mockSession.set('priya@example.com'))

describe('mock backend', () => {
  it('signs Priya in with her grants and admin flag', async () => {
    const me = await mockAuthApi.getMe()
    expect(me).toMatchObject({ name: 'Priya', is_admin: true })
    expect(me.grants.map((g) => g.scope_path)).toEqual(['org', 'org/team/ops', PRIYA])
  })

  it('previews, stores to the personal scope, and finds it only for its readers', async () => {
    const preview = await mockCaptureApi.preview({
      scope: null,
      input_type: 'text',
      config,
      content:
        "Acme Logistics ships to our Reno warehouse. Acme's lead time is 18 days, up from 10. I think the dock is closed today. It is late again.",
    })
    expect(preview.scope).toBe(PRIYA)
    expect(preview.extracted.length).toBeGreaterThan(2)
    expect(preview.extracted.some((f) => !f.storable)).toBe(true)
    expect(preview.extracted.some((f) => f.note?.startsWith('uncertain'))).toBe(true)
    expect(preview.corrections).toHaveLength(1)

    const kept = preview.extracted.filter((f) => f.storable).map((f) => f.id)
    const stored = await mockCaptureApi.store({
      preview_id: preview.preview_id,
      kept,
      config,
    })
    expect(stored.written).toBe(kept.length)
    expect(stored.history[0]).toMatchObject({ old_value: '10', new_value: '18 days' })

    const asPriya = await mockAskApi.ask({ q: 'acme lead time' })
    expect(asPriya.facts.some((f) => f.fact.includes('lead_time = 18 days'))).toBe(true)

    const asArun = await mockAskApi.ask({
      q: 'acme lead time',
      as_users: ['arun@example.com'],
    })
    expect(asArun.scopes).toEqual(['org', 'org/team/eng', ARUN])
    expect(JSON.stringify(asArun)).not.toContain('18 days')

    const together = await mockAskApi.ask({
      q: 'acme',
      as_users: ['priya@example.com', 'deena@example.com'],
    })
    expect(together.scopes).toEqual(['org', 'org/team/ops', PRIYA, DEENA])
  })

  it('refuses writes outside the grants, an unknown preview, and ask-as for non-admins', async () => {
    await expect(
      mockCaptureApi.preview({
        scope: 'org/team/ops',
        input_type: 'text',
        config,
        content: 'x',
      }),
    ).rejects.toMatchObject({ status: 403 })
    await expect(
      mockCaptureApi.store({ preview_id: 'prev_nope', kept: [], config }),
    ).rejects.toMatchObject({ status: 404 })

    mockSession.set('arun@example.com')
    await expect(
      mockAskApi.ask({ q: 'x', as_users: ['priya@example.com'] }),
    ).rejects.toMatchObject({ status: 403 })
    await expect(mockAdminApi.users()).rejects.toMatchObject({ status: 403 })
  })

  it('grants a new team scope, registering it and its parents, then revokes it', async () => {
    const user = await mockAdminApi.grant('arun@example.com', {
      scope_path: 'org/team/qa/',
      access: 'read',
      layer: 'team',
    })
    expect(user.grants.map((g) => g.scope_path)).toContain('org/team/qa')
    expect(MOCK_REGISTERED.has('org/team/qa')).toBe(true)

    await mockAdminApi.revoke('arun@example.com', 'org/team/qa')
    await expect(
      mockAdminApi.revoke('arun@example.com', 'org/team/qa'),
    ).rejects.toMatchObject({ status: 404 })
    await expect(
      mockAdminApi.grant('arun@example.com', {
        scope_path: 'elsewhere/x',
        access: 'read',
        layer: 'team',
      }),
    ).rejects.toMatchObject({ status: 422 })
  })

  it('signs in someone new with a personal scope and org read, then signs out', async () => {
    const me = await mockAuthApi.devLogin('hari.kumar@example.com', 'Hari Kumar')
    expect(me.grants).toEqual([
      { scope_path: 'org', access: 'read', layer: 'org', owner: null },
      {
        scope_path: 'org/user/hari_kumar',
        access: 'write',
        layer: 'personal',
        owner: 'Hari Kumar',
      },
    ])
    await mockAuthApi.logout()
    await expect(mockAuthApi.getMe()).rejects.toMatchObject({ status: 401 })
  })
})
