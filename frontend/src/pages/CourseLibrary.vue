<script setup lang="ts">
import { computed, ref } from 'vue'
import CourseCard from '../features/courses/components/CourseCard.vue'
import AppIcon from '../shared/components/AppIcon.vue'
import type { CourseSummary, CourseTask } from '../features/courses/types'
const props = defineProps<{
  courses: CourseSummary[]
  loading: boolean
  error: string
  tasks: Record<number, CourseTask | undefined>
}>()
defineEmits<{ create: []; retry: [] }>()
const search = ref('')
const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return props.courses.filter((course) =>
    `${course.name} ${course.intro}`.toLocaleLowerCase().includes(query),
  )
})
</script>

<template>
  <section class="library-page page-content">
    <header class="page-heading">
      <div>
        <p class="eyebrow">属于你的学习空间</p>
        <h1>把好奇，学成体系<span class="heading-dot">。</span></h1>
        <p class="page-description">从一个想法出发，建立课程，一点点走向理解。</p>
      </div>
      <button class="button primary" @click="$emit('create')">
        <AppIcon name="plus" />创建课程
      </button>
    </header>
    <div class="library-toolbar">
      <h2>
        我的课程 <span v-if="!loading && !error">{{ courses.length }}</span>
      </h2>
      <label v-if="courses.length" class="search-field"
        ><AppIcon name="search" /><input
          v-model="search"
          aria-label="搜索课程"
          placeholder="搜索课程"
          type="search"
      /></label>
    </div>
    <div v-if="loading" class="loading-state" role="status">
      <span class="spinner" />正在整理你的课程…
    </div>
    <div v-else-if="error" class="empty-state surface">
      <span class="empty-icon"><AppIcon name="book" /></span>
      <h2>暂时没有连接上学习空间</h2>
      <p role="alert">{{ error }}</p>
      <button class="button secondary" @click="$emit('retry')">重新连接</button>
    </div>
    <div v-else-if="!courses.length" class="first-course surface">
      <div class="empty-book" aria-hidden="true">
        <span class="book-spine" /><span class="book-cover"
          ><AppIcon name="book" /><span>一次新的探索</span><i /><i
        /></span>
      </div>
      <p class="eyebrow">留白，是学习的开始</p>
      <h2>第一门课，从你想了解的事开始</h2>
      <p>写下课程名称与目标，AI 会帮你梳理章节和小节。<br />你的课程与生成内容会自动保存。</p>
      <button class="button primary" @click="$emit('create')">
        <AppIcon name="plus" />创建第一门课程
      </button>
    </div>
    <div v-else-if="filtered.length" class="course-grid">
      <CourseCard
        v-for="course in filtered"
        :key="course.id"
        :course="course"
        :busy="!!tasks[course.id]"
      />
    </div>
    <div v-else class="empty-state surface">
      <AppIcon name="search" />
      <h2>没有找到相关课程</h2>
      <p>换个关键词，或查看全部课程。</p>
      <button class="button secondary" @click="search = ''">清除搜索</button>
    </div>
    <footer class="library-footer">
      <span class="footer-line" />按自己的节奏，慢慢建立理解。<span class="footer-line" />
    </footer>
  </section>
</template>

<style scoped>
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 14px 0 51px;
}
h1 {
  font-size: clamp(26px, 3vw, 37px);
  font-weight: 500;
  line-height: 1.5;
  margin: 16px 0 13px;
  letter-spacing: -1px;
}
.heading-dot {
  color: #809bae;
}
.page-description {
  font-size: 14px;
  color: var(--muted);
  line-height: 1.9;
}
.library-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 22px;
}
.library-toolbar h2 {
  font-size: 16px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.library-toolbar h2 span {
  color: var(--muted);
  border: 1px solid var(--line);
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 400;
}
.search-field {
  display: flex;
  gap: 9px;
  align-items: center;
  width: 220px;
  color: var(--muted);
}
.search-field input {
  background: transparent;
  border: 0;
  padding: 7px 0;
  border-radius: 0;
  font-size: 12px;
}
.search-field .app-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(290px, 100%), 1fr));
  gap: 22px;
}
.first-course {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 44px 24px 48px;
}
.first-course h2 {
  font-size: 21px;
  margin: 12px 0;
}
.first-course > p:not(.eyebrow) {
  font-size: 13px;
  color: var(--muted);
  line-height: 2;
  margin-bottom: 25px;
}
.empty-book {
  width: 110px;
  height: 125px;
  position: relative;
  margin-bottom: 25px;
  transform: rotate(-7deg);
}
.book-spine {
  position: absolute;
  inset: 9px 0 0 9px;
  background: #e8eef3;
  border: 1px solid #d9e2ea;
  border-radius: 4px 10px 10px 4px;
  transform: rotate(13deg);
}
.book-cover {
  position: absolute;
  inset: 0 7px 5px 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 19px 13px;
  border: 1px solid #d2dce5;
  border-left: 5px solid #c7d4df;
  border-radius: 4px 10px 10px 4px;
  background: #f9fbfd;
  color: #6e8ca3;
  box-shadow: 5px 9px 15px #4059750c;
}
.book-cover > span {
  font-size: 8px;
  margin: 14px 0 11px;
  letter-spacing: 1px;
}
.book-cover i {
  height: 2px;
  width: 50px;
  background: #dbe4eb;
  margin-bottom: 5px;
}
.book-cover i:last-child {
  width: 34px;
}
.library-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 17px;
  margin-top: 44px;
  color: #7d8a97;
  font-size: 11px;
}
.footer-line {
  width: 32px;
  height: 1px;
  background: var(--line);
}
@media (max-width: 740px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 22px;
    padding-bottom: 34px;
  }
  .page-heading h1 {
    margin-top: 10px;
  }
  .search-field {
    width: 155px;
  }
  .first-course {
    padding: 32px 20px;
  }
  .first-course h2 {
    font-size: 18px;
  }
}
</style>
