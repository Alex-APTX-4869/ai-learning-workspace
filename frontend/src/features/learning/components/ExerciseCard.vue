<script setup lang="ts">
import { computed, ref, watch, useId } from 'vue'
import type { ContentExercise } from '../types'
import SafeMarkdown from './SafeMarkdown.vue'

const props = defineProps<{ exercise: ContentExercise; number: number }>()
const selected = ref<number[]>([])
const answerName = useId()
const writtenAnswer = ref('')
const submitted = ref(false)

// 兼容还没有 kind/options 字段的早期已保存内容。
const kind = computed(() => props.exercise.kind || 'short_answer')
const options = computed(() => props.exercise.options || [])
const isShortAnswer = computed(() => kind.value === 'short_answer')
const isMultiple = computed(() => kind.value === 'multiple_choice')
const canSubmit = computed(() =>
  isShortAnswer.value ? !!writtenAnswer.value.trim() : selected.value.length > 0,
)
const correct = computed(() => {
  if (isShortAnswer.value) return null
  const expected = options.value
    .map((option, index) => (option.correct ? index : -1))
    .filter((index) => index >= 0)
  return (
    expected.length === selected.value.length &&
    expected.every((index) => selected.value.includes(index))
  )
})

watch(
  () => props.exercise,
  () => {
    selected.value = []
    writtenAnswer.value = ''
    submitted.value = false
  },
)

function choose(index: number, checked: boolean) {
  submitted.value = false
  if (!isMultiple.value) {
    selected.value = [index]
    return
  }
  selected.value = checked
    ? [...selected.value, index]
    : selected.value.filter((item) => item !== index)
}
</script>

<template>
  <article class="exercise-card">
    <span class="item-number">练习 {{ number }} · {{ isShortAnswer ? '解答题' : kind==='true_false' ? '判断题' : isMultiple ? '选择题 · 多选' : '选择题 · 单选' }}</span>
    <SafeMarkdown :source="exercise.question" />

    <fieldset v-if="!isShortAnswer" class="exercise-options" :class="{'judgment-options':kind==='true_false'}">
      <legend class="sr-only">请选择答案</legend>
      <label v-for="(option, index) in options" :key="`${index}-${option.label}`">
        <input
          :type="isMultiple ? 'checkbox' : 'radio'"
          :name="answerName"
          :checked="selected.includes(index)"
          @change="choose(index, ($event.target as HTMLInputElement).checked)"
        />
        <span><b v-if="kind!=='true_false'">{{ option.label }}</b>{{ option.text }}</span>
      </label>
    </fieldset>
    <textarea
      v-else
      v-model="writtenAnswer"
      class="written-answer"
      rows="4"
      placeholder="先写下你的思路，再查看参考答案"
      @input="submitted = false"
    />

    <details v-if="exercise.hint" class="exercise-detail">
      <summary>查看提示</summary>
      <SafeMarkdown :source="exercise.hint" />
    </details>

    <button
      type="button"
      class="button secondary small submit-answer"
      :disabled="!canSubmit"
      @click="submitted = true"
    >
      {{ isShortAnswer ? '查看参考答案' : '提交答案' }}
    </button>

    <section
      v-if="submitted"
      class="answer-feedback"
      :class="{ correct: correct === true, wrong: correct === false }"
      aria-live="polite"
    >
      <strong v-if="correct === true">回答正确</strong>
      <strong v-else-if="correct === false">还差一点，对照解析再想一遍</strong>
      <strong v-else>对照参考答案检查你的思路</strong>
      <div class="answer-part">
        <h4>参考答案</h4>
        <SafeMarkdown :source="exercise.answer" />
      </div>
      <div class="answer-part">
        <h4>解析</h4>
        <SafeMarkdown :source="exercise.explanation" />
      </div>
    </section>
  </article>
</template>

<style scoped>
.exercise-card {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #fff;
}
.item-number {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.5px;
}
.exercise-card > .safe-markdown {
  margin-top: 9px;
}
.exercise-options {
  display: grid;
  gap: 8px;
  margin-top: 16px;
  padding: 0;
  border: 0;
}
.exercise-options label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--body);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.7;
}
.judgment-options {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.exercise-options label:has(input:checked) {
  border-color: #aac0d0;
  background: var(--soft);
}
.exercise-options input {
  margin-top: 4px;
}
.exercise-options b {
  display: inline-block;
  min-width: 25px;
  color: var(--accent);
}
.written-answer {
  width: 100%;
  margin-top: 15px;
  resize: vertical;
  font-size: 13px;
  line-height: 1.7;
}
.exercise-detail {
  margin-top: 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}
.exercise-detail summary {
  padding: 10px 12px;
  cursor: pointer;
  color: var(--accent);
  font-size: 12px;
}
.exercise-detail > .safe-markdown {
  margin: 0 14px 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.submit-answer {
  margin-top: 14px;
}
.answer-feedback {
  margin-top: 15px;
  padding: 15px;
  border: 1px solid #dce5ec;
  border-radius: 9px;
  background: var(--soft);
  color: var(--body);
  font-size: 12px;
}
.answer-feedback.correct {
  border-color: #cfe2d7;
  background: #f3f9f5;
}
.answer-feedback.wrong {
  border-color: #eadfd5;
  background: #fcf8f3;
}
.answer-part {
  margin-top: 13px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.answer-part h4 {
  margin-bottom: 7px;
  color: var(--ink);
  font-size: 11px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
@media (max-width: 640px) {
  .exercise-card {
    padding: 16px;
  }
}
</style>
