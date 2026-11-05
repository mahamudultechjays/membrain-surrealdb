/**
 * The paths, and their parents down from `root`, that are not in `registered`,
 * parents first: the order Agent Memory creates them in. Paths outside `root`
 * are left to the backend, which refuses them with its own message.
 */
export function unregisteredScopes(
  paths: readonly string[],
  registered: ReadonlySet<string>,
  root: string,
): string[] {
  const rootDepth = root.split('/').length
  const missing: string[] = []
  for (const path of paths) {
    if (path !== root && !path.startsWith(root + '/')) continue
    const parts = path.split('/')
    for (let depth = rootDepth; depth <= parts.length; depth++) {
      const node = parts.slice(0, depth).join('/')
      if (!registered.has(node) && !missing.includes(node)) missing.push(node)
    }
  }
  return missing
}

/** Trimmed, without leading or trailing slashes: how the backend stores paths. */
export const cleanPath = (path: string) => path.trim().replace(/^\/+|\/+$/g, '')

/*
 * Naming rule for new scope names (standup, 5 Nov): lower case, words joined by
 * "_", nothing else. Typing is normalised as it happens (capitals go lower case,
 * spaces become "_") so the field always shows the real name; any other symbol
 * is left in place and reported, so the person fixes it rather than having it
 * silently rewritten.
 */

/**
 * What the name field shows for what was typed: lower case, with each space as
 * "_". Character for character, so the caret can stay where it was.
 */
export const typedScopeName = (text: string) => text.toLowerCase().replace(/\s/g, '_')

/** The scope name created from the field: tidy "_" runs and any "_" at the end. */
export const scopeName = (typed: string) =>
  typedScopeName(typed).replace(/_{2,}/g, '_').replace(/_+$/, '')

/** The characters a new scope name may not hold, each once, in typed order. */
export function invalidScopeChars(typed: string): string[] {
  return [...new Set(typedScopeName(typed).replace(/[a-z0-9_]/g, ''))]
}

/** Why `typed` can't be a scope name, or null when it can (or is still empty). */
export function scopeNameProblem(typed: string): string | null {
  const name = scopeName(typed)
  if (name === '') return null
  const bad = invalidScopeChars(typed)
  if (bad.length)
    return `Only lower-case letters, numbers and _ are allowed. Remove ${bad
      .map((c) => `“${c}”`)
      .join(' ')}.`
  if (name.startsWith('_')) return 'Start with a letter or a number.'
  return null
}

/** The name with every disallowed character swapped for "_", for a one-click fix. */
export const fixScopeName = (typed: string) =>
  scopeName(
    typedScopeName(typed)
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/^_+/, ''),
  )

/*
 * The same rule for a whole path typed in "Add scope": each part between "/" is
 * a name. "-" is allowed there too, since older scopes use it (lab/ske-a) and
 * the backend accepts it; new names made in New scope still can't have one.
 */

/** Characters a typed path may not hold, each once, in typed order. */
function invalidPathChars(typed: string): string[] {
  return [...new Set(typedScopeName(typed).replace(/[a-z0-9_/-]/g, ''))]
}

/** Why `typed` can't be a scope path, or null when it can (or is still empty). */
export function scopePathProblem(typed: string): string | null {
  const path = cleanPath(typedScopeName(typed))
  if (path === '') return null
  const bad = invalidPathChars(typed)
  if (bad.length)
    return `Only lower-case letters, numbers, _ and / are allowed. Remove ${bad
      .map((c) => `“${c}”`)
      .join(' ')}.`
  if (path.includes('//')) return 'Remove the empty part between “//”.'
  if (path.split('/').some((part) => /^[_-]/.test(part)))
    return 'Start each part with a letter or a number.'
  return null
}

/** The path with each disallowed run swapped for "_" and tidied, for a one-click fix. */
export const fixScopePath = (typed: string) =>
  cleanPath(typedScopeName(typed))
    .replace(/[^a-z0-9_/-]+/g, '_')
    .split('/')
    .map((part) => part.replace(/_{2,}/g, '_').replace(/^[_-]+|_+$/g, ''))
    .filter(Boolean)
    .join('/')

export interface ChildScope {
  name: string
  path: string
  /** Registered scopes further down, e.g. arun_das/demo under arun_das. */
  nested: number
}

/** The scopes one level under `parent`, by name, each with how many sit below it. */
export function childScopes(parent: string, paths: Iterable<string>): ChildScope[] {
  const prefix = `${parent}/`
  const nested = new Map<string, number>()
  for (const path of paths) {
    if (!path.startsWith(prefix)) continue
    const [name, ...rest] = path.slice(prefix.length).split('/')
    if (!name) continue
    nested.set(name, (nested.get(name) ?? 0) + (rest.length ? 1 : 0))
  }
  return [...nested]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, count]) => ({ name, path: prefix + name, nested: count }))
}
