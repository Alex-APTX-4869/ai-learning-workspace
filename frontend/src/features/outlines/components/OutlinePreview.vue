<script setup lang="ts">
import type { OutlineChapter } from '../types'

defineProps<{ chapters: OutlineChapter[]; live?: boolean }>()
</script>

<template>
  <div class="outline-preview" :aria-live="live ? 'polite' : undefined">
    <article v-for="(chapter, chapterIndex) in chapters" :key="`${chapterIndex}-${chapter.name}`">
      <header>
        <span>{{ String(chapterIndex + 1).padStart(2, '0') }}</span>
        <h4>{{ chapter.name }}</h4>
      </header>
      <ol v-if="chapter.sections.length">
        <li v-for="(section, sectionIndex) in chapter.sections" :key="`${sectionIndex}-${section.name}`">
          <span>{{ chapterIndex + 1 }}.{{ sectionIndex + 1 }}</span>{{ section.name }}
        </li>
      </ol>
      <p v-else-if="live">正在规划这一章的小节…</p>
    </article>
  </div>
</template>

<style scoped>
.outline-preview {
  display: grid;
  gap: 9px;
}
article {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}
header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 13px 15px;
  background: var(--soft);
}
header > span {
  color: #8a9cab;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
h4 {
  font-size: 13px;
  font-weight: 550;
  line-height: 1.6;
}
ol {
  margin: 0;
  padding: 5px 15px 9px;
  list-style: none;
}
li {
  display: flex;
  gap: 11px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line);
  color: var(--body);
  font-size: 12px;
  line-height: 1.6;
}
li:last-child {
  border-bottom: 0;
}
li span {
  flex-shrink: 0;
  color: #8c99a6;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
article > p {
  padding: 12px 15px;
  color: var(--muted);
  font-size: 11px;
}
</style>
