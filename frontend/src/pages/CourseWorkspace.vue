<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from '../shared/components/AppIcon.vue'
import ChapterList from '../features/courses/components/ChapterList.vue'
import LearningDialog from '../features/learning/components/LearningDialog.vue'
import MaterialsPanel from '../features/materials/components/MaterialsPanel.vue'
import {
  courseCounts,
  type Chapter,
  type Course,
  type CourseTask,
  type Section,
} from '../features/courses/types'
const props = defineProps<{ course: Course; task?: CourseTask; error?: string }>()
defineEmits<{ edit: []; generate: [chapterId?: number] }>()
const mode = ref('outline')
const sectionId = ref<number | null>(null)
const chapterId = ref<number | null>(null)
const counts = computed(() => courseCounts(props.course))
const chapter = computed(() => props.course.chapters.find((item) => item.id === chapterId.value))
const section = computed(() => chapter.value?.sections.find((item) => item.id === sectionId.value))
function openSection(section: Section, chapter: Chapter) {
  sectionId.value = section.id
  chapterId.value = chapter.id
}
</script>

<template>
  <section class="workspace-page page-content">
    <header class="workspace-heading">
      <div>
        <p class="eyebrow">课程工作台</p>
        <h1>{{ course.name }}</h1>
        <p class="course-intro">{{ course.intro }}</p>
        <div class="course-meta">
          <span>{{ counts.chapters }} 章</span><span>{{ counts.sections }} 小节</span
          ><span>{{ counts.points }} 个知识点</span
          ><span class="saved-indicator"><AppIcon name="check" />已保存</span>
        </div>
      </div>
      <button class="button secondary small" :disabled="!!task" @click="$emit('edit')">
        <AppIcon name="edit" />编辑信息
      </button>
    </header>
    <nav class="workspace-tabs" aria-label="课程页面">
      <button :aria-pressed="mode === 'outline'" @click="mode = 'outline'">
        <AppIcon name="book" />课程目录</button
      ><button :aria-pressed="mode === 'materials'" @click="mode = 'materials'">
        <AppIcon name="file" />参考资料
      </button>
    </nav>
    <div v-if="task" class="notice" role="status">
      <span class="spinner" /><span
        >{{ task.label }}… 完成后会自动保存，你可以继续浏览其他课程。</span
      >
    </div>
    <div v-if="error" class="notice error-message" role="alert">{{ error }}</div>
    <template v-if="mode === 'outline'">
      <div v-if="!course.chapters.length" class="outline-empty surface">
        <div class="outline-illustration" aria-hidden="true">
          <span>01 <i /></span><span>02 <i /></span><span>03 <i /></span>
        </div>
        <p class="eyebrow">先看见方向，再开始探索</p>
        <h2>为这门课，搭起一份清晰的目录</h2>
        <p>AI 将根据你的学习目标规划章节和小节。<br />目录就绪后，再逐章生成知识点。</p>
        <button class="button primary" :disabled="!!task" @click="$emit('generate')">
          <span v-if="task" class="spinner" /><AppIcon v-else name="sparkles" />{{
            task ? '正在规划目录' : '生成课程大纲'
          }}
        </button>
      </div>
      <template v-else
        ><div class="outline-caption"><span>课程大纲</span><span>点击小节，打开学习空间</span></div>
        <ChapterList
          :chapters="course.chapters"
          :task="task"
          @generate="$emit('generate', $event)"
          @open-section="openSection"
      /></template>
    </template>
    <MaterialsPanel v-else />
    <LearningDialog
      v-if="section && chapter"
      :section="section"
      :chapter="chapter"
      :course-name="course.name"
      :task="task"
      :error="error"
      @close="sectionId = null"
      @generate="$emit('generate', $event)"
    />
  </section>
</template>

<style scoped>
.workspace-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 28px;
  padding-top: 10px;
}
.workspace-heading > div {
  min-width: 0;
}
h1 {
  font-size: 32px;
  font-weight: 500;
  line-height: 1.5;
  margin: 14px 0;
  overflow-wrap: anywhere;
}
.course-intro {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.95;
  max-width: 680px;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.course-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 19px;
  font-size: 12px;
  color: var(--muted);
  margin-top: 24px;
}
.saved-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--accent);
}
.saved-indicator .app-icon {
  width: 14px;
  height: 14px;
}
.workspace-tabs {
  display: flex;
  gap: 30px;
  margin: 38px 0 28px;
  border-bottom: 1px solid var(--line);
}
.workspace-tabs button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  font-size: 13px;
  color: var(--muted);
}
.workspace-tabs button[aria-pressed='true'] {
  color: var(--ink);
  border-bottom-color: var(--accent);
}
.workspace-tabs .app-icon {
  width: 17px;
  height: 17px;
}
.outline-caption {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 18px;
}
.outline-caption span:first-child {
  color: var(--ink);
  font-size: 14px;
}
.outline-empty {
  text-align: center;
  padding: 42px 24px;
}
.outline-empty h2 {
  font-size: 21px;
  margin: 14px 0;
}
.outline-empty > p:not(.eyebrow) {
  font-size: 13px;
  line-height: 2;
  color: var(--muted);
  margin-bottom: 26px;
}
.outline-illustration {
  width: 165px;
  margin: 0 auto 30px;
  text-align: left;
}
.outline-illustration > span {
  display: flex;
  align-items: center;
  gap: 15px;
  font-size: 11px;
  color: #7c94a7;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  margin-bottom: 5px;
  background: var(--soft);
}
.outline-illustration i {
  height: 4px;
  width: 90px;
  border-radius: 2px;
  background: #dce5eb;
}
.outline-illustration > span:nth-child(2) {
  margin-left: 13px;
}
.outline-illustration > span:nth-child(3) {
  margin-left: 26px;
}
@media (max-width: 640px) {
  .workspace-heading {
    flex-direction: column;
    gap: 20px;
  }
  h1 {
    font-size: 26px;
  }
  .workspace-tabs {
    margin-top: 28px;
  }
  .outline-caption {
    font-size: 11px;
  }
  .outline-empty h2 {
    font-size: 18px;
  }
}
</style>
