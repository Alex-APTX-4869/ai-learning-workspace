<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { Point } from '../../courses/types'
import { isActiveLearningJob, type LearningJob, type PointContentVersion } from '../types'
import CodeLabPanel from './CodeLabPanel.vue'
import ExerciseCard from './ExerciseCard.vue'
import SafeMarkdown from './SafeMarkdown.vue'
import LearningGoals from './LearningGoals.vue'
import TutorPanel from '../../tutor/components/TutorPanel.vue'
import ContentSources from './ContentSources.vue'

const props = defineProps<{
  courseId: number
  guided?: boolean
  outlineVersionId: number | null
  nextPointName?: string
  point: Point
  content: PointContentVersion | null
  job: LearningJob | null
  loading: boolean
  starting: boolean
  cancelling: boolean
  loadError: string
  actionError: string
  statusText: string
}>()
const emit = defineEmits<{ start: []; cancel: []; retry: []; reload: []; nextPoint: []; guidedChange: [value: boolean] }>()

type ContentMode = 'lesson' | 'examples' | 'practice' | 'code-lab'
const mode = ref<ContentMode>('lesson')
const sourceItems = computed(() => {
  const value = props.content?.content
  if (!value) return []
  if (mode.value === 'examples') return value.examples
  if (mode.value === 'practice') return value.exercises.map((item, index) => ({ ...item, title: `练习 ${index + 1}` }))
  if (mode.value === 'code-lab') return value.code_lab ? [value.code_lab] : []
  return value.lesson_cards
})
const presentation = computed({get:()=>props.guided === false ? 'read' : 'guided',set:(value:'guided'|'read')=>emit('guidedChange',value==='guided')})
const canGuide = computed(() => !!props.content?.content.lesson_cards?.length)
const activeJob = computed(() => isActiveLearningJob(props.job))
const hasLegacyContent = computed(() => !props.content && !!props.point.content_markdown)
const terminalMessage = computed(() => {
  if (props.job?.status === 'needs_review') {
    return props.job.error || '自动审查后仍有问题，本次结果没有替换当前已保存内容。'
  }
  if (props.job?.status === 'failed') {
    return props.job.error || '生成没有完成，当前已保存内容保持不变。'
  }
  if (props.job?.status === 'needs_attention') {
    return props.job.error || '上次模型调用结果不确定，需要你确认后才会重试。'
  }
  if (props.job?.status === 'cancelled') {
    return props.job.error || '已停止本次生成，当前已保存内容保持不变。'
  }
  return ''
})

watch(
  () => [props.point.id, props.content?.id] as const,
  () => {
    mode.value = 'lesson'
  },
)
</script>

<template>
  <article class="point-content" :class="{ 'point-content-guided': canGuide && presentation === 'guided' }">
    <template v-if="!canGuide || presentation==='read'">
    <header class="point-heading">
      <div>
        <p class="eyebrow">专注此刻，理解一个知识点</p>
        <h2>{{ point.name }}</h2>
      </div>
      <div v-if="content || hasLegacyContent" class="heading-actions">
        <span v-if="content" class="plain-tag">
          {{ content.origin === 'legacy' ? '旧讲义' : `内容 V${content.version_number}` }}
        </span>
        <button
          type="button"
          class="button secondary small"
          :disabled="loading || starting || cancelling"
          @click="activeJob ? emit('cancel') : emit('start')"
        >
          <span v-if="starting || cancelling" class="spinner" />
          <AppIcon v-else name="sparkles" />
          {{
            cancelling
              ? '正在停止'
              : activeJob
                ? '停止生成'
                : starting
                  ? '正在启动'
                  : '重新生成内容'
          }}
        </button>
      </div>
    </header>

    <LearningGoals v-if="!canGuide || presentation==='read'" :intro="point.intro" :goals="content?.content.learning_goals" />

    <div v-if="content?.origin === 'legacy'" class="legacy-notice" role="note">
      <AppIcon name="info" />
      <span>这是此前保存的旧讲义，尚未经过新内容 Agent 审查；你可以继续阅读或重新生成。</span>
    </div>

    <div v-if="activeJob" class="generation-notice" role="status" aria-live="polite">
      <span class="spinner" />
      <div>
        <strong>{{ statusText }}</strong>
        <small v-if="content">生成期间继续显示已保存的内容 V{{ content.version_number }}。关闭页面不会中断。</small>
        <small v-else-if="hasLegacyContent">生成期间继续显示原有讲义。</small>
        <small v-else>完成并通过审查后，内容会自动出现在这里；关闭页面不会中断。</small>
      </div>
    </div>

    <div v-else-if="terminalMessage" class="terminal-notice" role="alert">
      <AppIcon name="info" />
      <div>
        <strong>{{ statusText }}</strong>
        <p>{{ terminalMessage }}</p>
        <div v-if="job?.status === 'needs_attention'" class="attention-actions">
          <button type="button" class="button primary small" :disabled="starting || cancelling" @click="emit('retry')">确认重试</button>
          <button type="button" class="button secondary small" :disabled="starting || cancelling" @click="emit('cancel')">放弃本次任务</button>
        </div>
      </div>
    </div>

    <div v-if="actionError" class="inline-error" role="alert">{{ actionError }}</div>
    <div v-if="loadError" class="inline-error load-error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" class="button secondary small" @click="emit('reload')">重新加载</button>
    </div>

    </template>
    <div v-if="loading && !content && !hasLegacyContent" class="content-loading" role="status">
      <span class="spinner" />正在读取这个知识点的内容…
    </div>

    <template v-else-if="content">
      <div v-if="!canGuide || presentation==='read'" class="presentation-switch" aria-label="学习方式">
        <button type="button" :aria-pressed="presentation === 'guided' && canGuide" :disabled="!canGuide" @click="presentation = 'guided'">讲师带学</button>
        <button type="button" :aria-pressed="presentation === 'read' || !canGuide" @click="presentation = 'read'">自主阅读</button>
        <small v-if="!canGuide">重新生成内容后可逐卡带学</small>
      </div>
      <TutorPanel v-if="canGuide && presentation === 'guided'" :key="content.id"
        :course-id="courseId" :outline-version-id="outlineVersionId"
        :point-id="point.id" :content-version-id="content.id"
        :material-evidence="content.content.material_evidence"
        :next-point-name="nextPointName" @next-point="emit('nextPoint')" @exit="emit('guidedChange',false)" />
      <template v-else>
      <nav class="content-tabs" aria-label="知识点内容类型">
        <button type="button" :aria-pressed="mode === 'lesson'" @click="mode = 'lesson'">
          讲解
        </button>
        <button
          v-if="content.content.examples.length"
          type="button"
          :aria-pressed="mode === 'examples'"
          @click="mode = 'examples'"
        >
          示例 <span>{{ content.content.examples.length }}</span>
        </button>
        <button
          v-if="content.content.exercises.length"
          type="button"
          :aria-pressed="mode === 'practice'"
          @click="mode = 'practice'"
        >
          练习 <span>{{ content.content.exercises.length }}</span>
        </button>
        <button
          v-if="content.content.code_lab"
          type="button"
          :aria-pressed="mode === 'code-lab'"
          @click="mode = 'code-lab'"
        >
          代码实验
        </button>
      </nav>

      <ContentSources :course-id="courseId" :outline-version-id="content.outline_version_id"
        :evidence="content.content.material_evidence" :items="sourceItems" />
      <div v-if="mode === 'lesson'" class="lesson-content">
        <SafeMarkdown :source="content.content.lesson_markdown" />
        <section class="lesson-summary" aria-labelledby="lesson-summary-title">
          <span class="tiny-heading">回顾</span>
          <h3 id="lesson-summary-title">本知识点总结</h3>
          <p>{{ content.content.summary }}</p>
        </section>
        <div class="review-result">
          <span :class="{ approved: content.review.approved }">
            <AppIcon :name="content.review.approved ? 'check' : 'info'" />
            {{
              content.review.approved
                ? '已通过内容审查'
                : content.origin === 'legacy'
                  ? '旧讲义尚未经过新内容 Agent 审查'
                  : '内容带有审查提醒'
            }}
          </span>
          <details
            v-if="content.review.issues.length || content.review.revision_instructions.length"
          >
            <summary>查看审查记录</summary>
            <div v-if="content.review.issues.length">
              <strong>发现的问题</strong>
              <ul>
                <li v-for="issue in content.review.issues" :key="issue">{{ issue }}</li>
              </ul>
            </div>
            <div v-if="content.review.revision_instructions.length">
              <strong>修订记录</strong>
              <ul>
                <li v-for="item in content.review.revision_instructions" :key="item">{{ item }}</li>
              </ul>
            </div>
          </details>
        </div>
      </div>

      <section v-else-if="mode === 'examples'" class="examples" aria-label="示例">
        <article v-for="(example, index) in content.content.examples" :key="`${index}-${example.title}`">
          <span class="item-number">示例 {{ index + 1 }}</span>
          <h3>{{ example.title }}</h3>
          <SafeMarkdown :source="example.explanation_markdown" />
          <div v-if="example.code" class="example-code">
            <span>{{ example.language || 'text' }}</span>
            <pre><code>{{ example.code }}</code></pre>
          </div>
        </article>
        <div v-if="!content.content.examples.length" class="quiet-empty">
          这个知识点不需要额外示例，完整说明已放在讲解中。
        </div>
      </section>

      <section v-else-if="mode === 'practice'" class="exercises" aria-label="练习">
        <ExerciseCard
          v-for="(exercise, index) in content.content.exercises"
          :key="index"
          :exercise="exercise"
          :number="index + 1"
        />
      </section>
      <CodeLabPanel v-else-if="content.content.code_lab" :lab="content.content.code_lab" />
      </template>
    </template>

    <section v-else-if="hasLegacyContent" class="legacy-content">
      <div class="legacy-heading">
        <span class="plain-tag">原有讲义</span>
        <p>下方是此前已保存的内容；生成新版期间不会清除。</p>
      </div>
      <SafeMarkdown :source="point.content_markdown!" />
    </section>

    <!-- 即使旧内容读取失败，活动任务仍必须保留显式停止入口。 -->
    <section v-else-if="activeJob || terminalMessage || !loadError" class="content-pending">
      <AppIcon name="book" />
      <h3>生成完整学习内容</h3>
      <p>内容 Agent 会先规划本小节，撰写讲解，并按教学需要增加示例、练习或代码实验。</p>
      <button
        type="button"
        class="button primary"
        :disabled="starting || cancelling"
        @click="activeJob ? emit('cancel') : emit('start')"
      >
        <span v-if="starting || cancelling" class="spinner" />
        <AppIcon v-else name="sparkles" />
        {{
          cancelling
            ? '正在停止'
            : activeJob
              ? '停止生成'
              : starting
            ? '正在启动'
              : terminalMessage
                ? '重新生成'
                : '开始生成内容'
        }}
      </button>
    </section>
  </article>
</template>

<style scoped>
.point-content {
  max-width: 850px;
  margin: 0 auto;
  padding: 34px 42px 48px;
}
.point-content-guided {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  max-width: none;
}
.point-content-guided > :not(.tutor-panel) { flex-shrink: 0; }
.point-content-guided .point-heading { align-items: center; gap: 8px; }
.point-content-guided .point-heading .eyebrow { display: none; }
.point-content-guided h2 { margin: 0; font-size: 18px; }
.point-content-guided .heading-actions { margin: 0; }
.point-content-guided .presentation-switch { margin-top: 10px; padding-bottom: 8px; }
.point-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}
.point-heading > div:first-child {
  min-width: 0;
}
h2 {
  margin: 10px 0 23px;
  font-size: 24px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.heading-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 9px;
  margin-bottom: 16px;
}
.presentation-switch { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; border-bottom: 1px solid var(--line); margin-top: 25px; padding-bottom: 12px; }
.presentation-switch button { padding: 8px 12px; border: 0; border-radius: 7px; background: transparent; color: var(--muted); font-size: 12px; }
.presentation-switch button[aria-pressed='true'] { background: #edf3f7; color: #456981; }
.presentation-switch small { color: var(--muted); font-size: 10px; margin-left: auto; }
.learning-objective {
  padding: 3px 0 3px 18px;
  border-left: 2px solid #b3c7d6;
}
.tiny-heading,
.item-number {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.5px;
}
.learning-objective p {
  margin-top: 8px;
  color: var(--body);
  font-size: 14px;
  line-height: 1.9;
}
.generation-notice,
.terminal-notice,
.legacy-notice,
.inline-error,
.content-loading {
  margin-top: 22px;
  border-radius: 9px;
  font-size: 12px;
  line-height: 1.7;
}
.generation-notice,
.terminal-notice,
.legacy-notice {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 13px 15px;
}
.generation-notice {
  border: 1px solid #dbe7ef;
  background: #f1f6f9;
  color: #4e7088;
}
.generation-notice .spinner {
  margin-top: 2px;
}
.generation-notice strong,
.generation-notice small {
  display: block;
}
.generation-notice small {
  margin-top: 2px;
  color: var(--muted);
}
.terminal-notice {
  border: 1px solid #eadfd5;
  background: #fcf8f3;
  color: #7b624e;
}
.legacy-notice {
  border: 1px solid #e4e4d8;
  background: #fbfbf5;
  color: #716f58;
}
.legacy-notice > .app-icon {
  width: 16px;
  margin-top: 2px;
}
.terminal-notice > .app-icon {
  width: 17px;
  margin-top: 2px;
}
.terminal-notice p {
  margin-top: 3px;
}
.inline-error {
  padding: 11px 13px;
  border: 1px solid #f0d9d7;
  background: #fdf4f3;
  color: var(--danger);
}
.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.content-loading {
  display: flex;
  min-height: 180px;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted);
}
.content-tabs {
  display: flex;
  gap: 26px;
  margin: 29px 0 27px;
  border-bottom: 1px solid var(--line);
}
.content-tabs button {
  padding: 0 0 12px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
}
.content-tabs button[aria-pressed='true'] {
  border-bottom-color: var(--accent);
  color: var(--ink);
}
.content-tabs button span {
  margin-left: 3px;
  color: #93a0ab;
  font-size: 10px;
}
.lesson-summary {
  margin-top: 30px;
  padding: 20px 21px;
  border: 1px solid #dfe8ee;
  border-radius: 11px;
  background: var(--soft);
}
.lesson-summary h3 {
  margin: 6px 0 8px;
  font-size: 16px;
}
.lesson-summary p {
  color: var(--body);
  font-size: 13px;
  line-height: 1.85;
  white-space: pre-wrap;
}
.review-result {
  margin-top: 16px;
  color: var(--muted);
  font-size: 11px;
}
.review-result > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.review-result > span.approved {
  color: var(--accent);
}
.review-result .app-icon {
  width: 14px;
}
.review-result details,
.exercise-detail {
  margin-top: 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}
summary {
  padding: 10px 12px;
  cursor: pointer;
  color: var(--accent);
  font-size: 12px;
}
.review-result details > div {
  padding: 0 14px 12px;
}
.review-result details > div + div {
  padding-top: 5px;
}
.review-result ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.7;
}
.examples,
.exercises {
  display: grid;
  gap: 15px;
}
.examples > article,
.exercise {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #fff;
}
.examples h3 {
  margin: 6px 0 11px;
  font-size: 17px;
}
.example-code {
  margin-top: 15px;
  overflow: hidden;
  border: 1px solid #dce5ec;
  border-radius: 9px;
  background: #f4f7f9;
}
.example-code > span {
  display: block;
  padding: 6px 12px;
  border-bottom: 1px solid #dce5ec;
  color: var(--muted);
  font-size: 10px;
}
.example-code pre {
  margin: 0;
  padding: 15px;
  overflow-x: auto;
  color: #31404d;
  font: 12px/1.75 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  tab-size: 2;
}
.quiet-empty {
  padding: 45px 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
.exercise > .safe-markdown {
  margin-top: 9px;
}
.exercise-detail > .safe-markdown,
.answer-detail .answer-part {
  margin: 0 14px 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.answer-detail .answer-part + .answer-part {
  margin-top: 16px;
}
.answer-part h4 {
  margin-bottom: 8px;
  color: var(--ink);
  font-size: 12px;
}
.legacy-content {
  margin-top: 28px;
}
.legacy-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  color: var(--muted);
  font-size: 11px;
}
.content-pending {
  padding: 50px 12px 25px;
  text-align: center;
  color: var(--muted);
}
.content-pending > .app-icon {
  width: 28px;
  height: 28px;
  color: #98aabc;
}
.content-pending h3 {
  margin: 17px 0 9px;
  color: var(--ink);
  font-size: 17px;
}
.content-pending p {
  max-width: 440px;
  margin: 0 auto 19px;
  font-size: 13px;
  line-height: 1.9;
}
@media (max-width: 640px) {
  .point-content {
    padding: 23px 20px 36px;
  }
  .point-content-guided { padding: 0; }
  .point-heading {
    flex-direction: column;
    gap: 0;
  }
  h2 {
    font-size: 22px;
  }
  .heading-actions {
    width: 100%;
    justify-content: space-between;
  }
  .content-tabs {
    gap: 19px;
    overflow-x: auto;
  }
  .content-tabs button {
    flex-shrink: 0;
  }
  .load-error,
  .legacy-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .examples > article,
  .exercise {
    padding: 16px;
  }
}
</style>
