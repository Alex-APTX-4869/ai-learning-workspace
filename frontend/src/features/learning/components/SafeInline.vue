<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ text: string }>()
const parts = computed(() => {
  const result: Array<{ kind: 'text' | 'code' | 'strong' | 'em'; text: string }> = []
  const expression = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g
  let start = 0
  for (const match of props.text.matchAll(expression)) {
    const index = match.index ?? 0
    if (index > start) result.push({ kind: 'text', text: props.text.slice(start, index) })
    result.push({ kind: match[1] ? 'code' : match[2] ? 'strong' : 'em', text: match[1] || match[2] || match[3] || '' })
    start = index + match[0].length
  }
  if (start < props.text.length) result.push({ kind: 'text', text: props.text.slice(start) })
  return result
})
</script>

<template>
  <template v-for="(part, index) in parts" :key="index">
    <code v-if="part.kind === 'code'">{{ part.text }}</code>
    <strong v-else-if="part.kind === 'strong'"><SafeInline v-if="part.text.includes('`')" :text="part.text" /><template v-else>{{ part.text }}</template></strong>
    <em v-else-if="part.kind === 'em'"><SafeInline v-if="part.text.includes('`')" :text="part.text" /><template v-else>{{ part.text }}</template></em>
    <template v-else>{{ part.text }}</template>
  </template>
</template>

<style scoped>
code { padding: 2px 5px; border-radius: 4px; background: #edf2f6; font: .9em ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
strong { color: var(--ink); font-weight: 600; }
</style>
