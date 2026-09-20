<script setup lang="ts">
import { computed } from 'vue'
import SafeInline from './SafeInline.vue'

type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'unordered-list' | 'ordered-list'; items: string[] }
  | { type: 'code'; language: string; code: string }
  | { type: 'table'; headers: string[]; rows: string[][] }

const props = defineProps<{ source: string }>()

function cells(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

function startsTable(lines: string[], index: number) {
  return lines[index]?.includes('|') && !!lines[index + 1]
    && cells(lines[index + 1]).every(cell => /^:?-{3,}:?$/.test(cell))
}

function startsBlock(line: string): boolean {
  return (
    /^\s*$/.test(line) ||
    /^\s*```/.test(line) ||
    /^\s{0,3}#{1,6}\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line)
  )
}

function parseMarkdown(source: string): MarkdownBlock[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const blocks: MarkdownBlock[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    if (startsTable(lines, index)) {
      const headers = cells(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(cells(lines[index]))
        index += 1
      }
      blocks.push({ type: 'table', headers, rows })
      continue
    }

    const fence = line.match(/^\s*```([^`]*)$/)
    if (fence) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        code.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push({ type: 'code', language: fence[1].trim(), code: code.join('\n') })
      continue
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ''))
        index += 1
      }
      blocks.push({ type: 'quote', text: quote.join('\n') })
      continue
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/)
    if (unordered) {
      const items: string[] = []
      while (index < lines.length) {
        const item = lines[index].match(/^\s*[-*+]\s+(.+)$/)
        if (!item) break
        items.push(item[1].trim())
        index += 1
      }
      blocks.push({ type: 'unordered-list', items })
      continue
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (ordered) {
      const items: string[] = []
      while (index < lines.length) {
        const item = lines[index].match(/^\s*\d+[.)]\s+(.+)$/)
        if (!item) break
        items.push(item[1].trim())
        index += 1
      }
      blocks.push({ type: 'ordered-list', items })
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (index < lines.length && !startsBlock(lines[index]) && !startsTable(lines, index)) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push({ type: 'paragraph', text: paragraph.join('\n').trim() })
  }

  return blocks
}

function headingTag(level: number) {
  if (level <= 2) return 'h3'
  if (level === 3) return 'h4'
  return 'h5'
}

const blocks = computed(() => parseMarkdown(props.source || ''))
</script>

<template>
  <div class="safe-markdown">
    <template v-for="(block, index) in blocks" :key="`${block.type}-${index}`">
      <component
        :is="headingTag(block.level)"
        v-if="block.type === 'heading'"
        class="markdown-heading"
      >
        <SafeInline :text="block.text" />
      </component>
      <p v-else-if="block.type === 'paragraph'" class="markdown-paragraph"><SafeInline :text="block.text" /></p>
      <blockquote v-else-if="block.type === 'quote'"><SafeInline :text="block.text" /></blockquote>
      <ul v-else-if="block.type === 'unordered-list'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex"><SafeInline :text="item" /></li>
      </ul>
      <ol v-else-if="block.type === 'ordered-list'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex"><SafeInline :text="item" /></li>
      </ol>
      <div v-else-if="block.type === 'code'" class="markdown-code">
        <span v-if="block.language">{{ block.language }}</span>
        <pre><code>{{ block.code }}</code></pre>
      </div>
      <div v-else-if="block.type === 'table'" class="markdown-table">
        <table><thead><tr><th v-for="(header, i) in block.headers" :key="i"><SafeInline :text="header" /></th></tr></thead>
          <tbody><tr v-for="(row, i) in block.rows" :key="i"><td v-for="(cell, j) in row" :key="j"><SafeInline :text="cell" /></td></tr></tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.safe-markdown {
  color: var(--body);
  font-size: 14px;
  line-height: 1.9;
  overflow-wrap: anywhere;
}
.safe-markdown > * + * {
  margin-top: 16px;
}
.markdown-table { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid var(--line); padding: 9px 11px; text-align: left; vertical-align: top; }
th { color: var(--ink); background: var(--soft); font-weight: 550; }
.markdown-heading {
  color: var(--ink);
  font-size: 17px;
  line-height: 1.55;
}
h4.markdown-heading {
  font-size: 15px;
}
h5.markdown-heading {
  font-size: 14px;
}
.markdown-paragraph,
blockquote {
  white-space: pre-wrap;
}
blockquote {
  padding: 3px 0 3px 15px;
  border-left: 2px solid #b8cbd9;
  color: var(--muted);
}
ul,
ol {
  padding-left: 24px;
}
li + li {
  margin-top: 6px;
}
.markdown-code {
  overflow: hidden;
  border: 1px solid #dce5ec;
  border-radius: 10px;
  background: #f4f7f9;
}
.markdown-code > span {
  display: block;
  padding: 7px 12px;
  border-bottom: 1px solid #dce5ec;
  color: var(--muted);
  font-size: 10px;
  text-transform: lowercase;
}
pre {
  margin: 0;
  padding: 15px;
  overflow-x: auto;
  color: #31404d;
  font: 12px/1.75 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  tab-size: 2;
  white-space: pre;
}
</style>
