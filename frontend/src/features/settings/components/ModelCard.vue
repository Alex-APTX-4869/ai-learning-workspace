<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { CAPABILITIES, DOCUMENT_CAPABILITIES, STATUS_LABELS } from '../modelCatalog'
import type {
  CapabilityName,
  ModelCapabilityDeclaration,
  ModelConfig,
} from '../types'

const props = defineProps<{
  model: ModelConfig
  busy: boolean
  saveCapabilities: (
    model: ModelConfig,
    capabilities: ModelCapabilityDeclaration,
  ) => Promise<boolean>
  verifyModel: (model: ModelConfig, capabilities: CapabilityName[]) => Promise<boolean>
}>()

const draft = reactive<ModelCapabilityDeclaration>({
  text_chat: false,
  structured_output: false,
  streaming: false,
  vision: false,
  embeddings: false,
})

function syncDraft() {
  for (const item of CAPABILITIES) draft[item.key] = props.model.capabilities[item.key].supported
}

watch(() => props.model.revision, syncDraft, { immediate: true })

const changed = computed(() =>
  CAPABILITIES.some(
    (item) => draft[item.key] !== props.model.capabilities[item.key].supported,
  ),
)
const supportedCapabilities = computed(() =>
  CAPABILITIES.filter((item) => props.model.capabilities[item.key].supported).map(
    (item) => item.key,
  ),
)
const hasUnverified = computed(() =>
  supportedCapabilities.value.some(
    (key) => props.model.capabilities[key].status !== 'verified',
  ),
)
const canProbeDocument = computed(() => DOCUMENT_CAPABILITIES.every(key => props.model.capabilities[key].supported))

async function save() {
  await props.saveCapabilities(props.model, { ...draft })
}

async function verify() {
  await props.verifyModel(props.model, supportedCapabilities.value)
}
</script>

<template>
  <article class="model-card" :class="{ disabled: !model.is_enabled }">
    <header>
      <div>
        <div class="model-title">
          <h4>{{ model.label }}</h4>
          <span v-if="!model.is_enabled" class="model-state">已停用</span>
        </div>
        <p>{{ model.model }}</p>
      </div>
      <span class="revision">配置版本 {{ model.revision }}</span>
    </header>

    <div class="capability-grid" aria-label="模型能力">
      <label v-for="item in CAPABILITIES" :key="item.key" :title="item.description">
        <input v-model="draft[item.key]" type="checkbox" :disabled="busy" />
        <span>
          <strong>{{ item.name }}</strong>
          <small
            v-if="model.capabilities[item.key].supported"
            :class="`state-${model.capabilities[item.key].status}`"
          >
            {{ STATUS_LABELS[model.capabilities[item.key].status] }}
          </small>
          <small v-else>未声明</small>
        </span>
      </label>
    </div>

    <div v-if="draft.vision" class="document-probe">
      <p>用于文档识别时，请声明文字对话、结构化结果和图片理解。专项检测只发送测试文字和本机合成的四色图，不发送你的资料，最多 3 次请求，可能产生费用。通过仅说明基础接口能力，不保证公式、图表的识别质量。</p>
      <button type="button" class="text-button" :disabled="busy || changed || !canProbeDocument || !model.is_enabled"
        @click="verifyModel(model, [...DOCUMENT_CAPABILITIES])">检测文档识别能力</button>
    </div>

    <footer>
      <p>
        能力由你声明；“已验证”只会由后端实际测试产生，测试可能产生少量费用。
        <template v-if="changed">请先保存本次修改。</template>
      </p>
      <div class="model-actions">
        <button
          type="button"
          class="text-button"
          :disabled="busy || changed || !supportedCapabilities.length"
          @click="verify"
        >
          {{ hasUnverified ? '验证已声明能力' : '重新验证' }}
        </button>
        <button
          v-if="changed"
          type="button"
          class="button secondary small"
          :disabled="busy"
          @click="save"
        >
          保存能力
        </button>
      </div>
    </footer>
  </article>
</template>

<style scoped>
.model-card {
  padding: 15px 16px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #fff;
}
.model-card.disabled {
  background: var(--soft);
}
.document-probe {border-top:1px solid var(--line);padding-top:10px;margin-bottom:10px;}
.document-probe p {font-size:10px;line-height:1.8;color:var(--muted);}
.document-probe button {margin-top:6px;}
header,
footer,
.model-title,
.model-actions {
  display: flex;
  align-items: center;
}
header,
footer {
  justify-content: space-between;
  gap: 14px;
}
h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 550;
}
.model-title {
  gap: 8px;
}
header p,
footer p {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.6;
}
header p {
  margin-top: 4px;
}
.revision,
.model-state {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 9px;
}
.model-state {
  color: var(--danger);
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
  margin: 14px 0;
}
.capability-grid label {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 6px;
  padding: 8px;
  border: 1px solid #edf1f4;
  border-radius: 8px;
  background: #fbfcfd;
  cursor: pointer;
}
.capability-grid input {
  width: auto;
  margin: 2px 0 0;
  padding: 0;
}
.capability-grid span,
.capability-grid strong,
.capability-grid small {
  display: block;
  min-width: 0;
}
.capability-grid strong {
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
}
.capability-grid small {
  margin-top: 3px;
  color: var(--muted);
  font-size: 8px;
  white-space: nowrap;
}
.capability-grid .state-verified {
  color: #4d8069;
}
.capability-grid .state-unverified {
  color: #9a713d;
}
.capability-grid .state-failed {
  color: var(--danger);
}
footer {
  align-items: flex-end;
  border-top: 1px solid #edf1f4;
  padding-top: 11px;
}
footer p {
  max-width: 390px;
}
.model-actions {
  flex-shrink: 0;
  gap: 9px;
}
.text-button {
  padding: 5px 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 10px;
}
.text-button:hover:not(:disabled) {
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (max-width: 900px) {
  .capability-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 620px) {
  .capability-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  footer {
    align-items: stretch;
    flex-direction: column;
  }
  .model-actions {
    justify-content: flex-end;
  }
}
</style>
