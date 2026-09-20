<script setup lang="ts">
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { QuestionOption } from '../types'
import SafeMarkdown from '../../learning/components/SafeMarkdown.vue'

defineProps<{
  option: QuestionOption | null
  explanation: string
  loading: boolean
  error: string
}>()
defineEmits<{ close: []; retry: [] }>()
</script>

<template>
  <aside class="explanation-panel" aria-labelledby="option-explanation-title">
    <header>
      <div>
        <p class="eyebrow">选项解释</p>
        <h3 id="option-explanation-title">{{ option?.title || '了解这个选项' }}</h3>
      </div>
      <button type="button" class="icon-button" aria-label="收起选项解释" @click="$emit('close')">
        <AppIcon name="close" />
      </button>
    </header>

    <div v-if="loading && !explanation" class="panel-state" role="status" aria-live="polite">
      <span class="spinner" />
      <p>AI 正在结合你的课程需求解释这个选项…</p>
    </div>

    <div v-if="error" class="panel-state panel-error" role="alert">
      <strong>{{ explanation ? '解释尚未完成' : '解释暂时没有生成' }}</strong>
      <p>{{ error }}</p>
      <button type="button" class="button secondary small" @click="$emit('retry')">重新解释</button>
    </div>

    <div v-if="explanation" class="explanation-content" :aria-busy="loading">
      <SafeMarkdown :source="explanation" />
      <p v-if="loading" role="status">正在继续解释…</p>
    </div>

    <p class="panel-note">解释用于帮助判断是否符合你的情况，不代表正确答案。</p>
  </aside>
</template>

<style scoped>
.explanation-panel {
  position: sticky;
  top: 0;
  align-self: start;
  min-width: 0;
  overflow-wrap: anywhere;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: #ffffffd9;
  box-shadow: 0 12px 30px #30485b0a;
}
header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 15px;
  border-bottom: 1px solid var(--line);
}
header h3 {
  margin-top: 5px;
  font-size: 15px;
  line-height: 1.5;
}
.panel-state {
  display: flex;
  min-height: 180px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 25px;
  text-align: center;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
.panel-error {
  color: var(--danger);
}
.panel-error strong {
  font-size: 13px;
}
.explanation-content {
  padding: 5px 18px 10px;
}
.explanation-content section {
  padding: 15px 0;
  border-bottom: 1px solid var(--line);
}
.explanation-content section:last-child {
  border-bottom: 0;
}
.explanation-content h4 {
  margin: 0 0 7px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 550;
  letter-spacing: 0.4px;
}
.explanation-content p {
  color: var(--body);
  font-size: 12px;
  line-height: 1.85;
  white-space: pre-line;
}
.plain-explanation p {
  color: var(--ink);
  font-size: 13px;
}
.panel-note {
  margin: 0 18px 17px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
}
@media (max-width: 820px) {
  .explanation-panel {
    position: static;
    width: 100%;
    max-height: none;
  }
}
</style>
