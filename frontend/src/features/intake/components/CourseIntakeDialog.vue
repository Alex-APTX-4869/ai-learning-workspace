<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { Course } from '../../courses/types'
import { useCourseIntake } from '../useCourseIntake'
import IntakeBriefStep from './IntakeBriefStep.vue'
import IntakeDepthStep from './IntakeDepthStep.vue'
import IntakeQuestionStep from './IntakeQuestionStep.vue'
import IntakeStartStep from './IntakeStartStep.vue'
import OptionExplanationPanel from './OptionExplanationPanel.vue'
import { useOptionExplanation } from '../useOptionExplanation'
import type { QuestionOption } from '../types'
import MaterialsUploadPanel from '../../materials/components/MaterialsUploadPanel.vue'
const materialState = ref({blocked: false, batchId: null as string|null, ideaLocked: false})

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: [course: Course] }>()
const {
  phase,
  initialName,
  initialIntro,
  session,
  selectedDepthId,
  customDepth,
  customQuestionCount,
  selectedOptionId,
  customAnswerSelected,
  customAnswer,
  busy,
  busyMessage,
  error,
  completedCourse,
  start,
  selectDepth,
  selectCustomDepth,
  submitDepth,
  selectAnswer,
  selectCustomAnswer,
  submitAnswer,
  confirm,
  retry,
  reset,
  restore,
} = useCourseIntake()
const {
  panelOpen: explanationOpen,
  selectedOption: explanationOption,
  explanation,
  loading: explanationLoading,
  error: explanationError,
  explain,
  retry: retryExplanation,
  closePanel: closeExplanation,
  reset: resetExplanation,
} = useOptionExplanation()

const phaseLabel = computed(() => {
  if (phase.value === 'start') return '课程想法'
  if (phase.value === 'depth') return '确认深度'
  if (phase.value === 'question') return '需求访谈'
  return '课程需求'
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetExplanation()
      restore()
    }
  },
  { immediate: true },
)

watch(
  () => session.value?.current_question?.id,
  (questionId, previousId) => {
    if (previousId && questionId !== previousId) resetExplanation()
  },
)

watch(completedCourse, (course) => {
  if (course) emit('saved', course)
})

function explainOption(option: QuestionOption) {
  const intake = session.value
  if (intake?.current_question) explain(intake.id, intake.current_question, option)
}

function restart() {
  resetExplanation()
  reset()
}
</script>

<template>
  <BaseDialog
    :open="open"
    wide
    labelledby="course-intake-title"
    :busy="busy"
    @close="emit('close')"
  >
    <div class="intake-shell">
      <header class="intake-header">
        <div>
          <p class="eyebrow">创建课程 · {{ phaseLabel }}</p>
          <h1 id="course-intake-title">把想学的事，变成一门适合你的课</h1>
        </div>
        <div class="header-actions">
          <button
            v-if="session"
            type="button"
            class="restart-button"
            :disabled="busy"
            @click="restart"
          >
            重新开始
          </button>
          <button
            class="icon-button"
            aria-label="关闭课程需求确认"
            :disabled="busy"
            @click="emit('close')"
          >
            <AppIcon name="close" />
          </button>
        </div>
      </header>

      <div class="intake-body">
        <IntakeStartStep
          v-if="phase === 'start'"
          v-model:name="initialName"
          v-model:intro="initialIntro"
          :busy="busy"
          :blocked="materialState.blocked"
          :idea-locked="materialState.ideaLocked"
          @submit="!materialState.blocked && start(materialState.batchId)"
        >
          <MaterialsUploadPanel v-if="open && !busy" :name="initialName" :intro="initialIntro"
            @state="materialState=$event" @restore-idea="(name,intro)=>{initialName=name;initialIntro=intro}" />
        </IntakeStartStep>

        <IntakeDepthStep
          v-else-if="phase === 'depth' && session"
          v-model:custom-question-count="customQuestionCount"
          :options="session.depth_options"
          :selected-id="selectedDepthId"
          :custom-selected="customDepth"
          :busy="busy"
          @select="selectDepth"
          @select-custom="selectCustomDepth"
          @submit="submitDepth"
        />

        <div
          v-else-if="phase === 'question' && session?.current_question"
          class="question-layout"
          :class="{ 'has-explanation': explanationOpen }"
        >
          <IntakeQuestionStep
            v-model:custom-answer="customAnswer"
            :question="session.current_question"
            :total="session.question_count || session.current_question.number"
            :selected-id="selectedOptionId"
            :custom-selected="customAnswerSelected"
            :busy="busy"
            :explanation-busy="explanationLoading"
            @select="selectAnswer"
            @select-custom="selectCustomAnswer"
            @explain="explainOption"
            @submit="submitAnswer"
          />
          <OptionExplanationPanel
            v-if="explanationOpen"
            :option="explanationOption"
            :explanation="explanation"
            :loading="explanationLoading"
            :error="explanationError"
            @close="closeExplanation"
            @retry="retryExplanation"
          />
        </div>

        <IntakeBriefStep
          v-else-if="phase === 'brief' && session?.brief"
          :brief="session.brief"
          :question-count="session.question_count || session.answers.length"
          :busy="busy"
          @confirm="confirm"
        />

        <div v-if="busyMessage" class="intake-status" role="status" aria-live="polite">
          <span class="spinner" />{{ busyMessage }}，请稍候…
        </div>
        <div v-if="error" class="intake-error" role="alert">
          <div>
            <strong>这一步没有完成</strong>
            <p>{{ error }}</p>
          </div>
          <button class="button secondary small" :disabled="busy" @click="retry">
            原地重试
          </button>
        </div>
      </div>
    </div>
  </BaseDialog>
</template>

<style scoped>
.intake-shell {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  background: linear-gradient(145deg, #ffffff 0%, #fbfcfd 55%, #f7fafc 100%);
}
.intake-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 28px;
  border-bottom: 1px solid var(--line);
  background: #ffffffc7;
}
.intake-header h1 {
  margin-top: 6px;
  font-size: 17px;
  line-height: 1.5;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}
.restart-button {
  padding: 7px 9px;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
}
.restart-button:hover:not(:disabled) {
  color: var(--ink);
}
.intake-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 34px 42px 38px;
}
.question-layout {
  display: grid;
  grid-template-columns: minmax(0, 760px);
  justify-content: center;
  gap: 18px;
  max-width: 1080px;
  margin: 0 auto;
}
.question-layout.has-explanation {
  grid-template-columns: minmax(0, 1fr) minmax(270px, 320px);
  justify-content: stretch;
}
.intake-status,
.intake-error {
  max-width: 900px;
  margin: 18px auto 0;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.7;
}
.intake-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 11px 15px;
  color: var(--accent);
  background: #eef4f8;
}
.intake-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 16px;
  border: 1px solid #f0d9d7;
  color: var(--danger);
  background: #fdf6f5;
}
.intake-error strong {
  font-size: 13px;
}
.intake-error p {
  margin-top: 3px;
}
@media (max-width: 640px) {
  .intake-header {
    padding: 17px 18px;
  }
  .intake-header h1 {
    max-width: 260px;
    font-size: 15px;
  }
  .intake-body {
    padding: 25px 18px 28px;
  }
  .intake-error {
    align-items: stretch;
    flex-direction: column;
  }
}
@media (max-width: 820px) {
  .question-layout,
  .question-layout.has-explanation {
    grid-template-columns: 1fr;
  }
}
</style>
