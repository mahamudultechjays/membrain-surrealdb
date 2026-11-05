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

/** One segment of a scope path, as the backend accepts it (SCOPE_PATH). */
export const SEGMENT = /^[a-z0-9][a-z0-9_-]*$/

/** A team name as a path segment: "Customer Support" -> "customer-support". */
export function teamSlug(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '')
}

/**
 * A person's name as a path segment, by the backend's rule for the personal
 * scope made at first sign-in (AccessService.personal_scope): first and last
 * word, "Priya Nair" -> "priya_nair". Something already shaped like a segment,
 * "arun_das", is kept as typed.
 */
export function personSlug(text: string): string {
  const typed = text.trim().toLowerCase()
  if (SEGMENT.test(typed)) return typed
  const words = typed
    .split(/\s+/)
    .map((word) => word.replace(/[^a-z0-9]/g, ''))
    .filter(Boolean)
  if (words.length > 1) return `${words[0]}_${words[words.length - 1]}`
  return words[0] ?? ''
}

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
