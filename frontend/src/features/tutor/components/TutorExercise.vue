<script setup lang="ts">
import { computed, ref, watch, useId } from 'vue'
import SafeMarkdown from '../../learning/components/SafeMarkdown.vue'
import type { ExerciseResponse, LearnerExercise } from '../types'

const props = defineProps<{ exercise: LearnerExercise; response: ExerciseResponse | null; disabled: boolean }>()
const emit = defineEmits<{ submit: [selected: number[], written: string] }>()
const selected = ref<number[]>([])
const answerName = useId()
const written = ref('')
const short = computed(() => props.exercise.kind === 'short_answer')
const valid = computed(() => short.value ? !!written.value.trim() : selected.value.length > 0)
watch(() => props.response, (response) => {
  selected.value = response?.selected ?? []
  written.value = response?.written_answer ?? ''
}, { immediate: true })
function choose(index: number) {
  selected.value = props.exercise.kind !== 'multiple_choice' ? [index]
    : selected.value.includes(index) ? selected.value.filter(item => item !== index) : [...selected.value, index]
}
</script>

<template>
  <section class="tutor-exercise">
    <span class="question-kind">{{ short ? '解答题' : exercise.kind === 'true_false' ? '判断题' : exercise.kind === 'multiple_choice' ? '选择题 · 多选' : '选择题 · 单选' }}</span>
    <SafeMarkdown :source="exercise.question" />
    <fieldset v-if="!short" :disabled="disabled" class="choices" :class="{'judgment-choices':exercise.kind==='true_false'}">
      <legend>选择你的答案</legend>
      <label v-for="(option, index) in exercise.options" :key="index" :class="{ selected: selected.includes(index) }">
        <input :type="exercise.kind === 'multiple_choice' ? 'checkbox' : 'radio'" :name="answerName"
          :checked="selected.includes(index)" @change="choose(index)" />
        <span><template v-if="exercise.kind!=='true_false'">{{ option.label }}. </template>{{ option.text }}</span>
      </label>
    </fieldset>
    <textarea v-else v-model="written" :disabled="disabled" rows="3" aria-label="我的作答"
      placeholder="写下你的理解，提交后对照参考答案" />
    <details v-if="exercise.hint"><summary>需要一点提示</summary><SafeMarkdown :source="exercise.hint" /></details>
    <button type="button" class="button secondary small" :disabled="disabled || !valid"
      @click="emit('submit', selected, written)">{{ response ? '重新提交' : short ? '提交并看参考答案' : '提交答案' }}</button>
    <div v-if="response" class="feedback" aria-live="polite">
      <strong>{{ response.correct === null ? '对照参考答案检查思路，也可以请讲师点评' : response.correct ? '回答正确' : '这次没有答对，对照解析再想一遍' }}</strong>
      <SafeMarkdown :source="response.answer" />
      <SafeMarkdown :source="response.explanation" />
    </div>
  </section>
</template>

<style scoped>
.question-kind { color: var(--muted); font-size: 11px; }
.tutor-exercise > * + * { margin-top: 14px; }
.choices { border: 0; padding: 0; display: grid; gap: 9px; }
legend { font-size: 11px; color: var(--muted); margin-bottom: 9px; }
.choices label { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; line-height: 1.7; font-size: 13px; cursor: pointer; }
.choices label.selected { background: var(--soft); border-color: #98b6ca; }
.choices input { width: auto; flex: 0 0 auto; margin: 5px 0 0; }
.judgment-choices {grid-template-columns:repeat(2,minmax(0,1fr));}
summary { cursor: pointer; color: var(--accent); font-size: 12px; }
details > .safe-markdown { margin-top: 10px; }
.feedback { padding: 16px; background: var(--soft); border-radius: 10px; }
.feedback strong { display: block; font-size: 13px; margin-bottom: 10px; }
.feedback > * + * { margin-top: 10px; }
</style>
