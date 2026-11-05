import {
  childScopes,
  fixScopeName,
  fixScopePath,
  scopeName,
  scopeNameProblem,
  scopePathProblem,
  typedScopeName,
} from '@/api/scopePaths'

describe('scope paths typed in Add scope', () => {
  it.each([
    ['org/spreetail/team/ops', null],
    ['org/spreetail/lab/ske-a', null],
    ['/org/spreetail/', null],
    ['', null],
    ['Org/Spreetail/Team Ops', null],
    [
      'org/spreetail/team!/ops',
      'Only lower-case letters, numbers, _ and / are allowed. Remove “!”.',
    ],
    ['org//spreetail', 'Remove the empty part between “//”.'],
    ['org/_x', 'Start each part with a letter or a number.'],
  ])('%j → %j', (typed, problem) => {
    expect(scopePathProblem(typed)).toBe(problem)
  })

  it('fixes a path in one click, part by part', () => {
    expect(fixScopePath('org/spreetail/Team & Ops!')).toBe('org/spreetail/team_ops')
    expect(fixScopePath('org//spreetail/_x/')).toBe('org/spreetail/x')
  })
})

describe('typedScopeName', () => {
  it.each([
    ['Customer Support', 'customer_support'],
    ['CAPS LOCK', 'caps_lock'],
    ['ops-finance', 'ops-finance'],
    ['a\tb', 'a_b'],
  ])('%j shows as %j', (typed, shown) => {
    expect(typedScopeName(typed)).toBe(shown)
    // Same length, so the caret can stay put while typing.
    expect(typedScopeName(typed)).toHaveLength(typed.length)
  })
})

describe('scopeName', () => {
  it.each([
    ['customer_support', 'customer_support'],
    ['customer_', 'customer'],
    ['two  spaces', 'two_spaces'],
    ['', ''],
  ])('%j -> %j', (typed, name) => expect(scopeName(typed)).toBe(name))
})

describe('scopeNameProblem', () => {
  it.each([
    ['customer_support', null],
    ['q4_2026', null],
    ['', null],
    ['ops-finance', 'Only lower-case letters, numbers and _ are allowed. Remove “-”.'],
    ['ops & r/d', 'Only lower-case letters, numbers and _ are allowed. Remove “&” “/”.'],
    ['_ops', 'Start with a letter or a number.'],
  ])('%j -> %j', (typed, problem) => expect(scopeNameProblem(typed)).toBe(problem))
})

describe('fixScopeName', () => {
  it.each([
    ['ops-finance', 'ops_finance'],
    ['Ops & Finance', 'ops_finance'],
    ['-ops-', 'ops'],
  ])('%j -> %j', (typed, fixed) => {
    expect(fixScopeName(typed)).toBe(fixed)
    expect(scopeNameProblem(fixed)).toBeNull()
  })
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
