<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { InterviewQuestion, QuestionOption } from '../types'

const props = defineProps<{
  question: InterviewQuestion
  total: number
  selectedId: string | null
  customSelected: boolean
  customAnswer: string
  busy: boolean
  explanationBusy: boolean
}>()
const emit = defineEmits<{
  select: [id: string]
  selectCustom: []
  'update:customAnswer': [value: string]
  explain: [option: QuestionOption]
  submit: []
}>()
const valid = computed(
  () => !!props.selectedId || (props.customSelected && !!props.customAnswer.trim()),
)
const progress = computed(() => `${Math.min(100, (props.question.number / props.total) * 100)}%`)
const recommendedOptionId = computed(
  () => props.question.options.find((option) => option.recommended)?.id ?? null,
)

function updateCustomAnswer(event: Event) {
  emit('update:customAnswer', (event.target as HTMLTextAreaElement).value)
}

function optionLetter(index: number) {
  let number = index + 1
  let label = ''
  while (number > 0) {
    number--
    label = String.fromCharCode(65 + number % 26) + label
    number = Math.floor(number / 26)
  }
  return `${label}.`
}
</script>

<template>
  <form class="intake-step" @submit.prevent="emit('submit')">
    <div class="progress-copy">
      <span>问题 {{ question.number }} / {{ total }}</span>
      <span class="progress-actions">
        <span>{{ Math.round((question.number / total) * 100) }}%</span>
      </span>
    </div>
    <div
      class="progress-track"
      role="progressbar"
      :aria-valuenow="question.number"
      aria-valuemin="1"
      :aria-valuemax="total"
      :aria-label="`需求确认进度：第 ${question.number} 题，共 ${total} 题`"
    >
      <span :style="{ width: progress }" />
    </div>

    <div class="question-heading">
      <p class="eyebrow">再清楚一点，课程就会更适合你</p>
      <h2>{{ question.text }}</h2>
      <p v-if="question.baseline" class="baseline">共同前提：{{ question.baseline }}</p>
      <p v-if="question.extension_reason" class="why" role="status">已自动增加 1 题：{{ question.extension_reason }}</p>
      <p v-if="question.purpose" class="why">
        <AppIcon name="sparkles" />为什么要问：{{ question.purpose }}
      </p>
      <p v-if="question.recommendation_reason" class="recommendation-reason">
        推荐依据：{{ question.recommendation_reason }}
      </p>
    </div>

    <fieldset :disabled="busy">
      <legend class="sr-only">请选择一个回答</legend>
      <div class="answer-list">
        <div
          v-for="(option, index) in question.options"
          :key="option.id"
          class="answer-row"
          :class="{ selected: selectedId === option.id }"
        >
          <label class="answer-choice">
            <input
              :id="`intake-answer-${index}`"
              type="radio"
              name="intake-answer"
              :checked="selectedId === option.id"
              @change="emit('select', option.id)"
            />
            <span class="answer-copy">
              <strong>
                <span class="choice-letter" aria-hidden="true">{{ optionLetter(index) }}</span>
                <span>{{ option.title }}</span>
                <span v-if="option.id === recommendedOptionId" class="option-recommended">推荐</span>
              </strong>
              <small v-if="option.description">{{ option.description }}</small>
            </span>
          </label>
          <button
            type="button"
            class="explain-button"
            :aria-label="`解释选项 ${optionLetter(index)} ${option.title}`"
            :disabled="busy"
            @click="emit('explain', option)"
          >
            解释
          </button>
        </div>

        <label class="answer-row custom-answer" :class="{ selected: customSelected }">
          <input
            type="radio"
            name="intake-answer"
            :checked="customSelected"
            @change="emit('selectCustom')"
          />
          <span class="answer-copy">
            <strong><span class="choice-letter" aria-hidden="true">其他：</span>自己输入</strong>
            <small>如果上面的选项都不准确，请按自己的情况回答。</small>
          </span>
        </label>
        <textarea
          v-if="customSelected"
          :value="customAnswer"
          rows="4"
          maxlength="1000"
          aria-label="自己输入的回答"
          placeholder="写下你的实际情况或想法"
          autofocus
          :disabled="busy"
          @input="updateCustomAnswer"
        />
      </div>
    </fieldset>

    <div class="step-actions">
      <button class="button primary" :disabled="!valid || busy">
        <span v-if="busy" class="spinner" />
        {{ busy ? '正在整理回答' : question.number >= total ? '完成需求确认' : '提交并看下一题' }}
        <AppIcon v-if="!busy" name="arrow" />
      </button>
    </div>
  </form>
</template>

<style scoped>
.intake-step {
  max-width: 760px;
  margin: 0 auto;
}
.progress-copy {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.progress-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.add-question {
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
}
.add-question:hover:not(:disabled) {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.question-limit {
  color: #8c99a6;
  font-size: 10px;
}
.progress-track {
  height: 3px;
  overflow: hidden;
  border-radius: 2px;
  background: #e8edf1;
}
.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 0.2s ease;
}
.question-heading {
  margin: 31px 0 24px;
}
.question-heading h2 {
  margin: 11px 0 15px;
  font-size: 24px;
  line-height: 1.55;
}
.why {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
.baseline {
  padding: 10px 14px;
  margin-bottom: 12px;
  border-left: 2px solid var(--accent);
  background: var(--soft);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.why .app-icon {
  width: 15px;
  height: 15px;
  margin-top: 3px;
  color: var(--accent);
}
.recommendation-reason {
  margin-top: 8px;
  padding-left: 23px;
  color: #71818e;
  font-size: 11px;
  line-height: 1.7;
}
fieldset {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.answer-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
}
.answer-row {
  position: relative;
  display: flex;
  align-items: stretch;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--surface);
  transition: border-color 0.15s, background 0.15s;
  overflow: hidden;
}
.answer-row:hover,
.answer-row.selected {
  border-color: #9fb5c6;
  background: #f8fbfd;
}
.answer-choice {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: flex-start;
  padding: 16px 18px;
  cursor: pointer;
}
.answer-choice > input,
.custom-answer > input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.answer-row:has(input:focus-visible) {
  outline: 2px solid #7b9eb9;
  outline-offset: 3px;
}
.choice-letter {
  margin-right: 7px;
  color: var(--accent);
  font-weight: 600;
}
.answer-copy {
  display: block;
  flex: 1;
  min-width: 0;
}
.answer-copy strong,
.answer-copy small {
  display: block;
}
.answer-copy strong {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  font-size: 13px;
  line-height: 1.6;
}
.answer-copy small {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.75;
}
.option-recommended {
  margin-left: 9px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #edf3f6;
  color: #607f94;
  font-size: 9px;
  font-weight: 500;
}
.explain-button {
  align-self: stretch;
  flex-shrink: 0;
  padding: 0 16px;
  border: 0;
  border-left: 1px solid var(--line);
  background: transparent;
  color: var(--accent);
  font-size: 11px;
}
.explain-button:hover:not(:disabled) {
  background: #eef4f7;
}
.custom-answer {
  align-items: flex-start;
  padding: 16px 18px;
  background: var(--soft);
  cursor: pointer;
}
.answer-list textarea {
  grid-column: 1 / -1;
  margin-top: -2px;
}
.step-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}
@media (max-width: 640px) {
  .answer-list {
    grid-template-columns: 1fr;
  }
  .answer-row {
    min-height: 0;
  }
  .progress-copy {
    align-items: flex-start;
  }
  .progress-actions {
    align-items: flex-end;
    flex-direction: column;
    gap: 4px;
  }
  .explain-button {
    padding-inline: 12px;
  }
  .question-heading h2 {
    font-size: 20px;
  }
  .step-actions .button {
    width: 100%;
  }
}
</style>
