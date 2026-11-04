import { Fragment, type ReactNode } from 'react'

/**
 * The Markdown Agent Memory's chat replies use: paragraphs, headings, bullet
 * and numbered lists (nested by indentation), **bold**, *italic*, `code`, and
 * [S1] source markers. Everything becomes React elements, so HTML in a reply
 * is shown as text, never run.
 */

interface ListNode {
  ordered: boolean
  items: { text: string; children: ListNode | null }[]
}

type Block =
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'heading'; text: string }
  | { kind: 'list'; list: ListNode }

const LIST_ITEM = /^(\s*)([*+-]|\d+[.)])\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/
const INLINE = /(\*\*[^*\n]+?\*\*|`[^`\n]+`|\[S\d+\]|\*[^*\s][^*\n]*?\*)/g

interface Entry {
  indent: number
  ordered: boolean
  text: string
}

function entryOf(line: string): Entry | null {
  const match = LIST_ITEM.exec(line)
  if (!match) return null
  return {
    indent: match[1]!.replace(/\t/g, '  ').length,
    ordered: /\d/.test(match[2]!),
    text: match[3]!,
  }
}

/** Consecutive list lines -> one list, nested wherever the indent grows. */
function buildList(entries: Entry[]): ListNode {
  const root: ListNode = { ordered: entries[0]!.ordered, items: [] }
  const stack = [{ indent: entries[0]!.indent, list: root }]
  for (const entry of entries) {
    while (stack.length > 1 && entry.indent < stack[stack.length - 1]!.indent) stack.pop()
    const top = stack[stack.length - 1]!
    const parent = top.list.items[top.list.items.length - 1]
    if (entry.indent > top.indent && parent) {
      const child: ListNode = { ordered: entry.ordered, items: [] }
      parent.children = child
      stack.push({ indent: entry.indent, list: child })
    }
    stack[stack.length - 1]!.list.items.push({ text: entry.text, children: null })
  }
  return root
}

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = []
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i]!
    if (!line.trim()) {
      i++
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ kind: 'heading', text: heading[1]! })
      i++
      continue
    }
    if (entryOf(line)) {
      const entries: Entry[] = []
      while (i < lines.length) {
        const entry = entryOf(lines[i]!)
        if (!entry) break
        entries.push(entry)
        i++
      }
      blocks.push({ kind: 'list', list: buildList(entries) })
      continue
    }
    const paragraph: string[] = []
    while (
      i < lines.length &&
      lines[i]!.trim() &&
      !entryOf(lines[i]!) &&
      !HEADING.test(lines[i]!)
    ) {
      paragraph.push(lines[i]!)
      i++
    }
    blocks.push({ kind: 'paragraph', lines: paragraph })
  }
  return blocks
}

type MarkerRenderer = (marker: string) => ReactNode

function inline(text: string, marker: MarkerRenderer): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (i % 2 === 0) return part ? <Fragment key={i}>{part}</Fragment> : null
    if (part.startsWith('**'))
      return <strong key={i}>{inline(part.slice(2, -2), marker)}</strong>
    if (part.startsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
    if (part.startsWith('['))
      return <Fragment key={i}>{marker(part.slice(1, -1))}</Fragment>
    return <em key={i}>{inline(part.slice(1, -1), marker)}</em>
  })
}

function List({ list, marker }: { list: ListNode; marker: MarkerRenderer }) {
  const items = list.items.map((item, i) => (
    <li key={i}>
      {inline(item.text, marker)}
      {item.children && <List list={item.children} marker={marker} />}
    </li>
  ))
  return list.ordered ? <ol>{items}</ol> : <ul>{items}</ul>
}

export default function ReplyText({
  text,
  marker,
}: {
  text: string
  marker: MarkerRenderer
}) {
  return (
    <>
      {parseBlocks(text).map((block, i) => {
        if (block.kind === 'heading')
          return (
            <p key={i} className="chat-heading">
              <strong>{inline(block.text, marker)}</strong>
            </p>
          )
        if (block.kind === 'list')
          return <List key={i} list={block.list} marker={marker} />
        return (
          <p key={i}>
            {block.lines.map((line, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(line, marker)}
              </Fragment>
            ))}
          </p>
        )
      })}
    </>
  )
}
