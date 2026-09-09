<script setup lang="ts">
defineProps<{
  name:
    | 'book'
    | 'plus'
    | 'arrow'
    | 'back'
    | 'close'
    | 'search'
    | 'sparkles'
    | 'file'
    | 'chevron'
    | 'check'
    | 'edit'
    | 'code'
    | 'grid'
}>()
const paths: Record<string, string> = {
  book: 'M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Zm0 0v14',
  plus: 'M12 5v14M5 12h14',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  back: 'M20 12H4m6-6-6 6 6 6',
  close: 'm6 6 12 12M6 18 18 6',
  search: 'm16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  sparkles: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4',
  file: 'M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6',
  chevron: 'm9 5 7 7-7 7',
  check: 'm5 12 4 4L19 6',
  edit: 'm15 4 5 5M4 20l5-1L21 7l-5-5L4 14v6Z',
  code: 'm8 6-6 6 6 6m8-12 6 6-6 6m-3-16-2 20',
  grid: 'M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z',
}
</script>

<template>
  <svg
    class="app-icon"
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name]" />
  </svg>
</template>
