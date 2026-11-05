import { childScopes, personSlug, teamSlug } from '@/api/scopePaths'

describe('teamSlug', () => {
  it.each([
    ['Customer Support', 'customer-support'],
    ['  QA / Core  ', 'qa-core'],
    ['ske-a', 'ske-a'],
    ['Ops & Finance', 'ops-finance'],
    ['!!!', ''],
  ])('%j -> %j', (typed, slug) => expect(teamSlug(typed)).toBe(slug))
})

describe('personSlug', () => {
  // The backend's rule for the personal scope made at first sign-in.
  it.each([
    ['Priya Nair', 'priya_nair'],
    ['Vidyul Narayanan P S', 'vidyul_s'],
    ['Priya', 'priya'],
    ["Siobhán O'Neil", 'siobhn_oneil'],
    ['arun_das', 'arun_das'],
    ['', ''],
  ])('%j -> %j', (typed, slug) => expect(personSlug(typed)).toBe(slug))
})

describe('childScopes', () => {
  it('lists one level down, counting what sits below each', () => {
    const paths = [
      'org/x',
      'org/x/user',
      'org/x/user/arun_das',
      'org/x/user/arun_das/demo',
      'org/x/user/arun_das/demo/q4',
      'org/x/user/binu',
      'org/x/team/ops',
    ]
    expect(childScopes('org/x/user', paths)).toEqual([
      { name: 'arun_das', path: 'org/x/user/arun_das', nested: 2 },
      { name: 'binu', path: 'org/x/user/binu', nested: 0 },
    ])
  })
})
