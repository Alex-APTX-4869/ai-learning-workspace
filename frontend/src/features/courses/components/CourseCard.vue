<script setup lang="ts">
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { CourseSummary } from '../types'

defineProps<{ course: CourseSummary; busy?: boolean }>()
</script>

<template>
  <a class="course-card" :href="`#/courses/${course.id}`">
    <span class="card-top"
      ><span class="course-symbol"><AppIcon name="book" /></span
      ><span class="status" :class="{ 'status-active': course.chapter_count || busy }"
        ><span class="status-dot" />{{
          busy ? '生成中' : course.chapter_count ? '已建目录' : '等待规划'
        }}</span
      ></span
    >
    <h2>{{ course.name }}</h2>
    <p class="card-intro">{{ course.intro }}</p>
    <span class="card-footer"
      ><span>{{
        course.chapter_count
          ? `${course.chapter_count} 章 · ${course.section_count} 小节`
          : '从课程大纲开始'
      }}</span
      ><span class="card-enter"><span>进入课程</span><AppIcon name="arrow" /></span
    ></span>
  </a>
</template>

<style scoped>
.course-card {
  display: flex;
  flex-direction: column;
  text-align: left;
  width: 100%;
  min-height: 258px;
  padding: 26px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: 0 3px 8px #23344902;
  transition:
    border-color 0.2s,
    box-shadow 0.2s,
    transform 0.2s;
  color: inherit;
  text-decoration: none;
}
.course-card:hover {
  border-color: #b8c8d5;
  box-shadow: 0 10px 28px #23344909;
  transform: translateY(-3px);
}
.card-top,
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.course-symbol {
  width: 42px;
  height: 42px;
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: 11px;
  display: grid;
  place-items: center;
  color: var(--accent);
}
h2 {
  font-size: 21px;
  font-weight: 550;
  line-height: 1.5;
  margin: 24px 0 9px;
  overflow-wrap: anywhere;
}
.card-intro {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 28px;
}
.card-footer {
  margin-top: auto;
  border-top: 1px solid var(--line);
  padding-top: 17px;
  font-size: 12px;
  color: var(--muted);
}
.card-enter {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
}
.card-enter .app-icon {
  width: 16px;
  height: 16px;
}
</style>
