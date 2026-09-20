<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import PointNavigation from './PointNavigation.vue'
import PointContent from './PointContent.vue'
import type { Chapter, CourseTask, Section } from '../../courses/types'
import { usePointContent } from '../usePointContent'
const props = defineProps<{
  courseId: number
  outlineVersionId: number | null
  section: Section
  chapter: Chapter
  courseName: string
  task?: CourseTask
  error?: string
}>()
const emit = defineEmits<{ close: []; generate: [chapterId: number] }>()
const selectedId = ref<number | null>(null)
const guided = ref(true)
const {
  content,
  job,
  loading,
  starting,
  cancelling,
  loadError,
  actionError,
  active,
  statusText,
  selectPoint,
  startJob,
  cancelJob,
  retryJob,
  reload,
  stop,
} = usePointContent()
const immersive = computed(() => guided.value && !!content.value?.content.lesson_cards?.length)
watch(
  () => props.section,
  (section) => {
    if (!section.points.some((point) => point.id === selectedId.value))
      selectedId.value = section.points[0]?.id ?? null
  },
  { immediate: true },
)
const point = computed(() => props.section.points.find((item) => item.id === selectedId.value))
const nextPoint = computed(() => {
  const index = props.section.points.findIndex((item) => item.id === selectedId.value)
  return index >= 0 ? props.section.points[index + 1] : undefined
})
watch(
  () => [props.courseId, props.outlineVersionId, point.value?.id ?? null] as const,
  ([courseId, outlineId, pointId]) => {
    if (pointId === null) stop()
    else void selectPoint(courseId, outlineId, pointId)
  },
  { immediate: true },
)

function close() {
  if (immersive.value) {
    guided.value = false
    return
  }
  stop()
  emit('close')
}
</script>

<template>
  <BaseDialog open wide :labelledby="immersive ? 'tutor-chat-title' : 'learning-title'" @close="close">
    <div class="learning-shell">
      <header v-if="!immersive" class="learning-header">
        <div class="learning-heading">
          <p>{{ courseName }} <span>/</span> {{ chapter.name }}</p>
          <h1 id="learning-title">{{ section.name }}</h1>
        </div>
        <button type="button" class="icon-button" aria-label="关闭学习弹窗" @click="close">
          <AppIcon name="close" />
        </button>
      </header>
      <div class="learning-body">
        <PointNavigation
          v-if="!immersive"
          :points="section.points"
          :selected-id="selectedId"
          @select="selectedId = $event"
        />
        <main class="learning-main">
          <PointContent
            v-if="point"
            :course-id="courseId"
            :guided="guided"
            @guided-change="guided = $event"
            :outline-version-id="outlineVersionId"
            :next-point-name="nextPoint?.name"
            :point="point"
            :content="content"
            :job="job"
            :loading="loading"
            :starting="starting"
            :cancelling="cancelling"
            :load-error="loadError"
            :action-error="actionError"
            :status-text="statusText"
            @start="startJob"
            @cancel="cancelJob"
            @retry="retryJob"
            @reload="reload"
            @next-point="nextPoint && (selectedId = nextPoint.id)"
          />
          <div v-else class="empty-state">
            <span class="empty-icon"><AppIcon name="sparkles" /></span>
            <h2>先展开这一章的知识点</h2>
            <p>AI 将为「{{ chapter.name }}」的各个小节梳理学习内容，完成后自动保存。</p>
            <button
              class="button primary"
              :disabled="!!task"
              @click="emit('generate', chapter.id)"
            >
              <span v-if="task" class="spinner" /><AppIcon v-else name="sparkles" />{{
                task ? task.label : '生成本章知识点'
              }}
            </button>
            <p v-if="error" class="error-message" role="alert">{{ error }}</p>
          </div>
        </main>
      </div>
      <footer v-if="!immersive" class="learning-footer">
        <span>{{ active ? statusText : `${section.points.length} 个知识点` }}</span
        ><span>关闭后回到课程目录 <kbd>Esc</kbd></span>
      </footer>
    </div>
  </BaseDialog>
</template>

<style scoped>
.learning-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.learning-header {
  flex-shrink: 0;
  padding: 24px 28px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  border-bottom: 1px solid var(--line);
}
.learning-heading {
  min-width: 0;
}
.learning-heading p {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.learning-heading p span {
  margin: 0 8px;
  color: #c5ced6;
}
h1 {
  font-size: 20px;
  line-height: 1.5;
  margin-top: 8px;
  overflow-wrap: anywhere;
}
.learning-body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.learning-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}
.learning-main:has(.point-content-guided) {
  overflow: hidden;
  min-height: 0;
}
.learning-footer {
  flex-shrink: 0;
  padding: 12px 25px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: var(--muted);
  font-size: 11px;
}
kbd {
  font: inherit;
  border: 1px solid var(--line);
  padding: 2px 4px;
  border-radius: 4px;
  margin-left: 8px;
}
@media (max-width: 640px) {
  .learning-body {
    flex-direction: column;
  }
  .learning-header {
    padding: 18px;
  }
  h1 {
    font-size: 17px;
  }
  .learning-footer {
    padding: 10px 15px;
  }
  .learning-footer kbd {
    display: none;
  }
}
</style>
