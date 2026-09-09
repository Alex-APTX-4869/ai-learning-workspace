<script setup lang="ts">
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { Chapter, CourseTask, Section } from '../types'
defineProps<{ chapters: Chapter[]; task?: CourseTask }>()
defineEmits<{ generate: [chapterId: number]; openSection: [section: Section, chapter: Chapter] }>()
</script>

<template>
  <div class="chapter-list">
    <section v-for="(chapter, index) in chapters" :key="chapter.id" class="chapter">
      <header class="chapter-header">
        <span class="chapter-number">{{ String(index + 1).padStart(2, '0') }}</span>
        <div class="chapter-title">
          <h2>{{ chapter.name }}</h2>
          <span>{{ chapter.sections.length }} 个小节</span>
        </div>
        <span
          v-if="chapter.sections.every((section) => section.points.length)"
          class="chapter-ready"
          ><AppIcon name="check" />知识点已就绪</span
        >
        <button
          v-else
          class="button subtle small"
          :disabled="!!task"
          @click="$emit('generate', chapter.id)"
        >
          <span v-if="task?.chapterId === chapter.id" class="spinner" /><AppIcon
            v-else
            name="sparkles"
          />{{
            task?.chapterId === chapter.id
              ? '正在生成'
              : chapter.sections.some((section) => section.points.length)
                ? '继续生成知识点'
                : '生成知识点'
          }}
        </button>
      </header>
      <div class="section-list">
        <button
          v-for="(section, sectionIndex) in chapter.sections"
          :key="section.id"
          class="section-row"
          @click="$emit('openSection', section, chapter)"
        >
          <span class="section-number">{{ index + 1 }}.{{ sectionIndex + 1 }}</span
          ><span class="section-name">{{ section.name }}</span
          ><span class="section-count">{{
            section.points.length ? `${section.points.length} 个知识点` : '待生成知识点'
          }}</span
          ><AppIcon name="chevron" />
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chapter-list {
  display: grid;
  gap: 20px;
}
.chapter {
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
  background: var(--surface);
}
.chapter-header {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 24px 26px;
}
.chapter-number {
  font-size: 25px;
  color: #a3b0bc;
  font-weight: 350;
  font-variant-numeric: tabular-nums;
  align-self: flex-start;
  line-height: 1.3;
}
.chapter-title {
  flex: 1;
  min-width: 0;
}
.chapter-title h2 {
  font-size: 17px;
  margin-bottom: 6px;
  overflow-wrap: anywhere;
}
.chapter-title > span {
  color: var(--muted);
  font-size: 12px;
}
.chapter-ready {
  font-size: 12px;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 5px;
}
.chapter-ready .app-icon {
  width: 15px;
}
.section-list {
  padding: 0 18px 14px;
}
.section-row {
  display: flex;
  width: 100%;
  text-align: left;
  align-items: center;
  padding: 17px 12px;
  gap: 16px;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--line);
  border-radius: 0;
  transition: background 0.15s;
}
.section-row:hover {
  background: var(--soft);
  border-radius: 8px;
}
.section-number {
  color: var(--muted);
  font-size: 12px;
  min-width: 30px;
  font-variant-numeric: tabular-nums;
}
.section-name {
  flex: 1;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.section-count {
  font-size: 12px;
  color: var(--muted);
}
.section-row .app-icon {
  width: 14px;
  color: var(--muted);
}
@media (max-width: 640px) {
  .chapter-header {
    padding: 20px 16px;
    gap: 12px;
    flex-wrap: wrap;
  }
  .chapter-title {
    min-width: 60%;
  }
  .chapter-header .button,
  .chapter-ready {
    margin-left: 39px;
  }
  .section-list {
    padding: 0 8px 8px;
  }
  .section-row {
    gap: 9px;
  }
  .section-count {
    display: none;
  }
}
</style>
