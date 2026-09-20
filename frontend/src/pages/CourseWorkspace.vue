<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '../shared/components/AppIcon.vue'
import ChapterList from '../features/courses/components/ChapterList.vue'
import CourseInfoPanel from '../features/courses/components/CourseInfoPanel.vue'
import LearningDialog from '../features/learning/components/LearningDialog.vue'
import MaterialsPanel from '../features/materials/components/MaterialsPanel.vue'
import OutlineVersionPanel from '../features/outlines/components/OutlineVersionPanel.vue'
import {
  courseCounts,
  type Chapter,
  type Course,
  type CourseTask,
  type Section,
} from '../features/courses/types'
const props = defineProps<{ course: Course; task?: CourseTask; error?: string }>()
defineEmits<{ edit: []; generate: [chapterId: number]; refresh: []; versionChanged: [course: Course] }>()
type WorkspaceMode = 'outline' | 'info' | 'materials'
const mode = ref<WorkspaceMode>('outline')
const sectionId = ref<number | null>(null)
const chapterId = ref<number | null>(null)
const introElement = ref<HTMLElement | null>(null)
const infoRegion = ref<HTMLElement | null>(null)
const introOverflow = ref(false)
let introObserver: ResizeObserver | null = null
const counts = computed(() => courseCounts(props.course))
const chapter = computed(() => props.course.chapters.find((item) => item.id === chapterId.value))
const section = computed(() => chapter.value?.sections.find((item) => item.id === sectionId.value))
function openSection(section: Section, chapter: Chapter) {
  sectionId.value = section.id
  chapterId.value = chapter.id
}

function measureIntro() {
  const element = introElement.value
  introOverflow.value = !!element && element.scrollHeight > element.clientHeight + 1
}

async function openCourseInfo() {
  mode.value = 'info'
  await nextTick()
  infoRegion.value?.focus({ preventScroll: true })
  infoRegion.value?.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start',
  })
}

onMounted(async () => {
  await nextTick()
  measureIntro()
  if (typeof ResizeObserver !== 'undefined' && introElement.value) {
    introObserver = new ResizeObserver(measureIntro)
    introObserver.observe(introElement.value)
  }
})
watch(
  () => props.course.intro,
  () => nextTick(measureIntro),
)
onBeforeUnmount(() => introObserver?.disconnect())
</script>

<template>
  <section class="workspace-page page-content">
    <header class="workspace-heading">
      <div>
        <h1>{{ course.name }}</h1>
        <div class="intro-summary">
          <p ref="introElement" class="course-intro">{{ course.intro }}</p>
          <small v-if="course.intro_is_fallback" class="history-fallback">
            此迁移前历史版本未保存独立简介，当前显示课程现用简介。
          </small>
          <button v-if="introOverflow" type="button" class="intro-more" @click="openCourseInfo">
            查看更多
          </button>
        </div>
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
      <button type="button" :aria-pressed="mode === 'outline'" @click="mode = 'outline'">
        <AppIcon name="book" />课程目录</button
      ><button type="button" :aria-pressed="mode === 'info'" @click="mode = 'info'">
        <AppIcon name="info" />课程信息</button
      ><button type="button" :aria-pressed="mode === 'materials'" @click="mode = 'materials'">
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
      <OutlineVersionPanel :course-id="course.id" @refresh="$emit('refresh')"
        @version-changed="$emit('versionChanged', $event)" />
      <template v-if="course.chapters.length"
        ><div class="outline-caption">
          <span>已制作的课程内容</span><span>点击小节，打开学习空间</span>
        </div>
        <ChapterList
          :chapters="course.chapters"
          :task="task"
          @generate="$emit('generate', $event)"
          @open-section="openSection"
      /></template>
      <div v-else class="materialization-note surface">
        <AppIcon name="book" />
        <div>
          <h2>知识点内容尚未制作</h2>
          <p>上方大纲以版本保存；确认结构后，后续步骤会基于所选版本制作知识点与讲解。</p>
        </div>
      </div>
    </template>
    <div v-else-if="mode === 'info'" ref="infoRegion" class="info-region" tabindex="-1">
      <CourseInfoPanel :course="course" />
    </div>
    <MaterialsPanel v-else :course-id="course.id" :outline-version-id="course.outline_version_id" />
    <LearningDialog
      v-if="section && chapter"
      :course-id="course.id"
      :outline-version-id="course.outline_version_id"
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
  margin: 0 0 12px;
  overflow-wrap: anywhere;
}
.intro-summary {
  max-width: 680px;
}
.course-intro {
  display: -webkit-box;
  max-height: calc(1.95em * 3);
  overflow: hidden;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.95;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.intro-more {
  margin-top: 5px;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
}
.history-fallback {
  display: block;
  margin-top: 5px;
  color: var(--muted);
  font-size: 10px;
}
.intro-more:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
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
  margin: 38px 0 10px;
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
.materialization-note {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px 22px;
  color: var(--muted);
}
.materialization-note > .app-icon {
  width: 20px;
  color: var(--accent);
}
.materialization-note h2 {
  margin-bottom: 5px;
  color: var(--ink);
  font-size: 14px;
}
.materialization-note p {
  font-size: 11px;
  line-height: 1.8;
}
.info-region {
  scroll-margin-top: 20px;
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
    gap: 16px;
    margin-top: 28px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .workspace-tabs button {
    flex-shrink: 0;
    font-size: 12px;
  }
  .outline-caption {
    font-size: 11px;
  }
}
</style>
