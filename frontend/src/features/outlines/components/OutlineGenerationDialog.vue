<script setup lang="ts">
import { ref, watch } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import type { OutlineChapter, OutlineGenerationInput, OutlineVersion } from '../types'
import OutlinePreview from './OutlinePreview.vue'

const props = defineProps<{
  open: boolean
  versions: OutlineVersion[]
  chapters: OutlineChapter[]
  generating: boolean
  saved: boolean
  status: string
  error: string
}>()
const emit = defineEmits<{
  close: []
  cancel: []
  generate: [input: OutlineGenerationInput]
}>()
const additionalRequirements = ref('')
const referenceVersionId = ref('')
let lastInput: OutlineGenerationInput | null = null

watch(
  () => props.open,
  (open) => {
    if (!open) return
    lastInput = null
  },
)

function currentInput(): OutlineGenerationInput {
  const requirements = additionalRequirements.value.trim()
  return {
    additional_requirements: requirements,
    reference_version_id: referenceVersionId.value ? Number(referenceVersionId.value) : null,
  }
}

function submit() {
  const input = currentInput()
  lastInput = input
  emit('generate', input)
}

function retry() {
  if (lastInput) emit('generate', lastInput)
}
</script>

<template>
  <BaseDialog
    :open="open"
    wide
    labelledby="outline-generation-title"
    :busy="generating"
    @close="emit('close')"
  >
    <div class="generation-dialog">
      <header class="dialog-header">
        <div>
          <p class="eyebrow">AI 课程设计</p>
          <h1 id="outline-generation-title">{{ versions.length ? '重新生成课程大纲' : '生成课程大纲' }}</h1>
          <p>新结果会保存为独立版本，生成失败不会留下半成品。</p>
        </div>
        <button
          type="button"
          class="icon-button"
          aria-label="关闭大纲生成窗口"
          :disabled="generating"
          @click="emit('close')"
        >
          <AppIcon name="close" />
        </button>
      </header>

      <div class="dialog-body">
        <form class="generation-form" @submit.prevent="submit">
          <label for="outline-requirements">本次附加要求（可选）</label>
          <textarea
            id="outline-requirements"
            v-model="additionalRequirements"
            rows="4"
            maxlength="12000"
            :disabled="generating"
            placeholder="例如：增加动手练习；先讲前后端通信，再引入 Agent。"
          />

          <label for="reference-version">是否参考已有版本？</label>
          <select id="reference-version" v-model="referenceVersionId" :disabled="generating">
            <option value="">不参考，从头规划</option>
            <option v-for="version in versions" :key="version.id" :value="version.id">
              参考 V{{ version.version_number }} · {{ version.name }}
            </option>
          </select>
          <p class="reference-note">参考版本只提供上下文，新结果仍会成为一个独立版本。</p>

          <div class="generation-actions">
            <button
              v-if="generating"
              type="button"
              class="button secondary"
              @click="emit('cancel')"
            >
              取消生成
            </button>
            <button class="button primary" :disabled="generating">
              <span v-if="generating" class="spinner" />
              <AppIcon v-else name="sparkles" />
              {{ generating ? '正在生成课程大纲' : '开始生成' }}
            </button>
          </div>
        </form>

        <section class="stream-column" aria-labelledby="stream-preview-title">
          <div class="stream-heading">
            <div>
              <span>实时预览</span>
              <span class="persistence-state" :class="{ saved }">
                {{ saved ? '已保存' : chapters.length || generating ? '预览 · 尚未保存' : '尚未开始' }}
              </span>
              <h2 id="stream-preview-title">章节与小节</h2>
            </div>
            <p v-if="generating || status" class="stream-status" role="status" aria-live="polite">
              <span v-if="generating" class="spinner" />
              <AppIcon v-else-if="saved" name="check" />
              <span v-else class="status-dot" />{{ status || '正在等待第一个章节…' }}
            </p>
          </div>

          <div v-if="!chapters.length && !generating && !error" class="preview-empty">
            开始后，模型返回的章节和小节会逐项出现在这里。
          </div>
          <div v-else-if="!chapters.length && generating" class="preview-empty" role="status">
            <span class="spinner" />正在等待第一个章节…
          </div>
          <OutlinePreview v-else-if="chapters.length" :chapters="chapters" live />

          <div v-if="error" class="stream-error" role="alert">
            <div>
              <strong>这次生成没有完成</strong>
              <p>{{ error }}</p>
            </div>
            <button
              type="button"
              class="button secondary small"
              :disabled="generating || !lastInput"
              @click="retry"
            >
              原地重试
            </button>
          </div>
        </section>
      </div>
    </div>
  </BaseDialog>
</template>

<style scoped>
.generation-dialog {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  background: linear-gradient(145deg, #fff, #f8fafc);
}
.dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 27px;
  border-bottom: 1px solid var(--line);
  background: #ffffffdc;
}
.dialog-header h1 {
  margin: 6px 0 5px;
  font-size: 19px;
}
.dialog-header > div > p:last-child {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}
.dialog-body {
  display: grid;
  min-height: 0;
  flex: 1;
  grid-template-columns: minmax(270px, 0.72fr) minmax(0, 1.28fr);
}
.generation-form {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 9px;
  padding: 27px;
  border-right: 1px solid var(--line);
}
.generation-form label {
  color: var(--body);
  font-size: 11px;
}
.generation-form label:not(:first-child) {
  margin-top: 11px;
}
.generation-form textarea {
  font-size: 12px;
}
select {
  width: 100%;
  min-width: 0;
  padding: 10px 34px 10px 11px;
  border: 1px solid #dce4eb;
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  font: inherit;
  font-size: 12px;
}
.reference-note {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
}
.generation-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 12px;
}
.stream-column {
  min-width: 0;
  overflow-y: auto;
  padding: 27px;
}
.stream-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
}
.stream-heading > div > span {
  color: var(--muted);
  font-size: 10px;
}
.stream-heading .persistence-state {
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--line);
  color: #947761;
}
.stream-heading .persistence-state.saved {
  color: var(--accent);
}
.stream-heading h2 {
  margin-top: 5px;
  font-size: 15px;
}
.stream-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--accent);
  font-size: 10px;
  text-align: right;
}
.stream-status .app-icon {
  width: 14px;
}
.preview-empty {
  display: flex;
  min-height: 260px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 28px;
  border: 1px dashed #d8e1e8;
  border-radius: 11px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
  text-align: center;
}
.stream-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 14px;
  padding: 13px 14px;
  border: 1px solid #f0d9d7;
  border-radius: 9px;
  background: #fdf4f3;
  color: var(--danger);
}
.stream-error strong {
  font-size: 12px;
}
.stream-error p {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.7;
}
@media (max-width: 760px) {
  .dialog-header {
    padding: 18px;
  }
  .dialog-body {
    display: block;
    overflow-y: auto;
  }
  .generation-form,
  .stream-column {
    padding: 20px 18px;
  }
  .generation-form {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .generation-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }
  .generation-actions .button {
    width: 100%;
  }
  .stream-column {
    overflow: visible;
  }
  .stream-heading,
  .stream-error {
    align-items: stretch;
    flex-direction: column;
  }
  .stream-status {
    text-align: left;
  }
}
</style>
