<script setup lang="ts">
import type { CourseSummary } from '../types'

defineProps<{
  courses: CourseSummary[]
  currentCourseId: number | null
  loading: boolean
}>()
</script>

<template>
  <nav class="sidebar-courses" aria-label="我的课程列表">
    <p v-if="loading && !courses.length" class="sidebar-state" role="status">正在加载课程…</p>
    <p v-else-if="!courses.length" class="sidebar-state">还没有课程</p>
    <a
      v-for="course in courses"
      v-else
      :key="course.id"
      :href="`#/courses/${course.id}`"
      class="sidebar-course"
      :class="{ current: currentCourseId === course.id }"
      :aria-current="currentCourseId === course.id ? 'page' : undefined"
      :title="course.name"
    >
      <span class="course-dot" aria-hidden="true" />
      <span class="course-name">{{ course.name }}</span>
      <span class="course-count">{{ course.chapter_count }}章</span>
    </a>
  </nav>
</template>

<style scoped>
.sidebar-courses {
  display: grid;
  gap: 3px;
  max-height: min(34dvh, 280px);
  margin: 7px 2px 0 10px;
  padding: 3px 5px 3px 2px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #cad5de transparent;
}
.sidebar-course {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border-radius: 7px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.4;
  text-decoration: none;
}
.sidebar-course:hover {
  color: var(--ink);
  background: #eef3f6;
}
.sidebar-course.current {
  color: #3f627a;
  background: #e6eef3;
  font-weight: 550;
}
.course-dot {
  width: 4px;
  height: 4px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #a7b5c0;
}
.current .course-dot {
  background: var(--accent);
}
.course-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.course-count {
  flex: 0 0 auto;
  color: #94a1ad;
  font-size: 9px;
}
.sidebar-state {
  padding: 9px;
  color: #8a98a5;
  font-size: 10px;
}
@media (max-width: 760px) {
  .sidebar-courses {
    display: none;
  }
}
</style>
