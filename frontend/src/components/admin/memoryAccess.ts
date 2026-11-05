/**
 * A person's own grants in Agent Memory, as rows for the Scope column. They
 * are read only here, and apply when the person reaches Agent Memory directly
 * (Claude Code, MCP); this app reads and writes through its own grants.
 */

/** "memory:read" → "Read memory", for the permissions Agent Memory has today. */
export const PERMISSION_LABELS: Record<string, string> = {
  'memory:read': 'Read memory',
  'memory:write': 'Write memory',
  'memory:forget': 'Forget memory',
  'scope:read': 'See scopes',
  'scope:create': 'Create scopes',
  'scope:delete': 'Delete scopes',
  'grant:manage': 'Manage access',
}

/** One scope pattern and what the person may do there. */
export interface MemoryRow {
  pattern: string
  /** The scope path, as this app writes them: "/*" → "/", "org/*" → "org". */
  path: string
  /** True when the pattern also covers every scope inside the path. */
  inside: boolean
  permissions: string[]
  /** "read & write", "read", or a count when memory can't be read there. */
  access: string
  writes: boolean
}

/** "/org/spreetail/*" → { path: "org/spreetail", inside: true }; "/*" → "/". */
export function scopeOf(pattern: string): { path: string; inside: boolean } {
  const inside = pattern.endsWith('*')
  const path = pattern.replace(/\*$/, '').replace(/^\/+|\/+$/g, '')
  return { path: path || '/', inside }
}

/**
 * One row per scope pattern, not per scope: "/*" covers every scope, present
 * and future, so it stays one row. Broadest patterns first.
 */
export function memoryRows(grants: Record<string, string[]>): MemoryRow[] {
  const byPattern = new Map<string, string[]>()
  for (const [permission, patterns] of Object.entries(grants)) {
    for (const pattern of patterns) {
      byPattern.set(pattern, [...(byPattern.get(pattern) ?? []), permission])
    }
  }
  return [...byPattern]
    .map(([pattern, permissions]) => ({
      pattern,
      ...scopeOf(pattern),
      permissions,
      access: accessOf(permissions),
      writes: permissions.includes('memory:write'),
    }))
    .sort(
      (a, b) => a.pattern.length - b.pattern.length || a.pattern.localeCompare(b.pattern),
    )
}

/** Worded as this app's grants are; the rest of the permissions go in the tooltip. */
function accessOf(permissions: string[]): string {
  if (permissions.includes('memory:write')) return 'read & write'
  if (permissions.includes('memory:read')) return 'read'
  return `${permissions.length} permission${permissions.length === 1 ? '' : 's'}`
}

/** The permissions, readable, for a tooltip. */
export const describe = (permissions: string[]) =>
  permissions.map((p) => PERMISSION_LABELS[p] ?? p).join(', ')
