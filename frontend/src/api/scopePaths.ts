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
