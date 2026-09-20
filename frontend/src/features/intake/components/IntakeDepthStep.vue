<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { DepthOption } from '../types'

const props = defineProps<{
  options: DepthOption[]
  selectedId: string | null
  customSelected: boolean
  customQuestionCount: number
  busy: boolean
}>()
const emit = defineEmits<{
  select: [id: string]
  selectCustom: []
  'update:customQuestionCount': [value: number]
  submit: []
}>()
const customCountValid = computed(
  () => Number.isInteger(props.customQuestionCount) && props.customQuestionCount >= 1 && props.customQuestionCount <= 20,
)
const valid = computed(() => !!props.selectedId || (props.customSelected && customCountValid.value))

function updateCount(event: Event) {
  emit('update:customQuestionCount', Number((event.target as HTMLInputElement).value))
}
</script>

<template>
  <form class="intake-step" @submit.prevent="emit('submit')">
    <div class="step-copy">
      <p class="eyebrow">选择需求确认深度</p>
      <h2>你希望我们把课程想得多细？</h2>
      <p>问题越多，课程会更贴合你的基础、目标和偏好。每一题都会根据此前回答动态生成，你也可以自己决定数量。</p>
    </div>

    <fieldset :disabled="busy">
      <legend class="sr-only">需求确认深度</legend>
      <div class="depth-grid">
        <label
          v-for="(option, index) in options"
          :key="option.id"
          class="depth-card"
          :class="{ selected: selectedId === option.id }"
        >
          <input
            :id="`intake-depth-${index}`"
            type="radio"
            name="intake-depth"
            :checked="selectedId === option.id"
            @change="emit('select', option.id)"
          />
          <span class="depth-top">
            <strong>{{ option.title }}</strong>
            <span v-if="option.recommended" class="recommended">推荐</span>
          </span>
          <span class="depth-description">{{ option.description }}</span>
          <span class="question-count">{{ option.question_count }} 个问题</span>
          <AppIcon v-if="selectedId === option.id" name="check" />
        </label>
      </div>

      <div class="custom-depth" :class="{ selected: customSelected }">
        <label>
          <input
            type="radio"
            name="intake-depth"
            :checked="customSelected"
            @change="emit('selectCustom')"
          />
          <span>
            <strong>自定义问题数量</strong>
            <small>在 1～20 题之间选择</small>
          </span>
        </label>
        <input
          type="number"
          min="1"
          max="20"
          step="1"
          :value="customQuestionCount"
          aria-label="自定义问题数量"
          @focus="emit('selectCustom')"
          @input="updateCount"
        />
        <span>题</span>
      </div>
    </fieldset>

    <div class="step-actions">
      <button class="button primary" :disabled="!valid || busy">
        <span v-if="busy" class="spinner" />
        {{ busy ? '正在准备问题' : '开始确认需求' }}
        <AppIcon v-if="!busy" name="arrow" />
      </button>
    </div>
  </form>
</template>

<style scoped>
.intake-step {
  max-width: 960px;
  margin: 0 auto;
}
.step-copy {
  margin-bottom: 27px;
}
.step-copy h2 {
  margin: 11px 0 8px;
  font-size: 25px;
}
.step-copy > p:last-child {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.85;
}
fieldset {
  min-width: 0;
  border: 0;
  padding: 0;
  margin: 0;
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
.depth-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 13px;
}
.depth-card {
  position: relative;
  display: flex;
  min-height: 190px;
  flex-direction: column;
  padding: 21px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.depth-card:hover,
.depth-card.selected,
.custom-depth.selected {
  border-color: #9fb5c6;
  background: #f8fbfd;
}
.depth-card.selected {
  box-shadow: 0 8px 24px #334b5f0a;
}
.depth-card > input,
.custom-depth label > input[type='radio'] {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.depth-card:has(input:focus-visible),
.custom-depth:has(input:focus-visible) {
  outline: 2px solid #7b9eb9;
  outline-offset: 3px;
}
.depth-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 15px;
}
.recommended {
  padding: 3px 7px;
  border-radius: 5px;
  background: #e9f0f5;
  color: var(--accent);
  font-size: 10px;
  font-weight: 500;
}
.depth-description {
  margin-top: 15px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
.question-count {
  margin-top: auto;
  padding-top: 18px;
  color: var(--accent);
  font-size: 12px;
}
.depth-card > .app-icon {
  position: absolute;
  right: 17px;
  bottom: 17px;
  width: 16px;
  height: 16px;
  color: var(--accent);
}
.custom-depth {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--soft);
  cursor: pointer;
}
.custom-depth label {
  display: flex;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.custom-depth label > span {
  flex: 1;
  min-width: 0;
}
.custom-depth strong,
.custom-depth small {
  display: block;
}
.custom-depth strong {
  font-size: 13px;
}
.custom-depth small {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
}
.custom-depth input[type='number'] {
  width: 72px;
  padding: 8px 10px;
  text-align: center;
  background: var(--surface);
}
.custom-depth > span:last-child {
  color: var(--muted);
  font-size: 12px;
}
.step-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 25px;
}
@media (max-width: 760px) {
  .depth-grid {
    grid-template-columns: 1fr;
  }
  .depth-card {
    min-height: 0;
  }
}
@media (max-width: 640px) {
  .step-copy h2 {
    font-size: 21px;
  }
  .custom-depth {
    flex-wrap: wrap;
  }
  .step-actions .button {
    width: 100%;
  }
}
</style>
