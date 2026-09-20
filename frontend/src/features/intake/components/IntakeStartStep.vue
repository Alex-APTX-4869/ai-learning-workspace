<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'

const props = defineProps<{ name: string; intro: string; busy: boolean; blocked?: boolean; ideaLocked?: boolean }>()
const emit = defineEmits<{
  'update:name': [value: string]
  'update:intro': [value: string]
  submit: []
}>()
const valid = computed(() => !!props.name.trim() && !!props.intro.trim())

function updateName(event: Event) {
  emit('update:name', (event.target as HTMLInputElement).value)
}

function updateIntro(event: Event) {
  emit('update:intro', (event.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <form class="intake-step start-step" @submit.prevent="emit('submit')">
    <div class="step-copy">
      <p class="eyebrow">先告诉我，你想探索什么</p>
      <h2>从一个还不够清晰的想法开始</h2>
      <p>不必先想好完整课程。AI 会通过几个问题，与你一起把学习目标理清。</p>
    </div>

    <label for="intake-course-name">课程名称</label>
    <input
      id="intake-course-name"
      :value="name"
      maxlength="200"
      placeholder="例如：系统学习 FastAPI"
      required
      autofocus
      :disabled="busy || ideaLocked"
      @input="updateName"
    />

    <label for="intake-course-intro">目前的想法或需求</label>
    <textarea
      id="intake-course-intro"
      :value="intro"
      rows="6"
      maxlength="12000"
      placeholder="可以写得模糊一些，例如：我会一点 Python，想学会做一个能接入 AI 的后端项目。"
      required
      :disabled="busy || ideaLocked"
      @input="updateIntro"
    />
    <p class="field-hint">你的回答会用于确定课程范围、学习深度和完成标准。</p>
    <slot />

    <div class="step-actions">
      <button class="button primary" :disabled="!valid || busy || blocked">
        <span v-if="busy" class="spinner" />
        <AppIcon v-else name="sparkles" />
        {{ busy ? '正在分析需求' : '让 AI 帮我理清需求' }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.intake-step {
  max-width: 690px;
  margin: 0 auto;
}
.step-copy {
  margin-bottom: 32px;
}
.step-copy h2 {
  margin: 11px 0 9px;
  font-size: 25px;
  line-height: 1.5;
}
.step-copy > p:last-child,
.field-hint {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
}
label {
  display: block;
  margin: 20px 0 9px;
  font-size: 13px;
  font-weight: 550;
}
.field-hint {
  margin-top: 9px;
  font-size: 12px;
}
.step-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 30px;
}
@media (max-width: 640px) {
  .step-copy h2 {
    font-size: 21px;
  }
  .step-actions .button {
    width: 100%;
  }
}
</style>
