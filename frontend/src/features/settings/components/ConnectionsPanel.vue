<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import { CAPABILITIES } from '../modelCatalog'
import type {
  CapabilityName,
  LlmProvider,
  ModelCapabilityDeclaration,
  ModelConfig,
  ModelConfigInput,
} from '../types'
import ModelCard from './ModelCard.vue'

const props = defineProps<{
  providers: LlmProvider[]
  models: ModelConfig[]
  mutation: string
  createProvider: (input: {
    name: string
    base_url: string
    model: string
    api_key: string
  }) => Promise<LlmProvider | null>
  createModel: (providerId: number, input: ModelConfigInput) => Promise<boolean>
  saveCapabilities: (
    model: ModelConfig,
    capabilities: ModelCapabilityDeclaration,
  ) => Promise<boolean>
  verifyModel: (model: ModelConfig, capabilities: CapabilityName[]) => Promise<boolean>
}>()

const selectedKey = ref('')
const addingProvider = ref(false)
const addingModel = ref(false)
const connectionName = ref('')
const baseUrl = ref('')
const firstModel = ref('')
const apiKey = ref('')
const modelLabel = ref('')
const modelId = ref('')
const modelCapabilities = reactive<ModelCapabilityDeclaration>({
  text_chat: true,
  structured_output: true,
  streaming: true,
  vision: false,
  embeddings: false,
})

const providerKey = (provider: LlmProvider) =>
  provider.id === null ? 'environment' : `provider:${provider.id}`

watch(
  () => props.providers,
  (providers) => {
    if (providers.some((item) => providerKey(item) === selectedKey.value)) return
    const preferred = providers.find((item) => item.id !== null && item.is_active)
      || providers.find((item) => item.id !== null)
      || providers[0]
    selectedKey.value = preferred ? providerKey(preferred) : ''
  },
  { immediate: true },
)

const selectedProvider = computed(() =>
  props.providers.find((item) => providerKey(item) === selectedKey.value),
)
const selectedModels = computed(() => {
  const id = selectedProvider.value?.id
  return id === null || id === undefined
    ? []
    : props.models.filter((item) => item.provider_id === id)
})
const providerValid = computed(
  () =>
    !!connectionName.value.trim()
    && !!baseUrl.value.trim()
    && !!firstModel.value.trim()
    && !!apiKey.value.trim(),
)
const modelValid = computed(
  () =>
    !!modelLabel.value.trim()
    && !!modelId.value.trim()
    && CAPABILITIES.some((item) => modelCapabilities[item.key]),
)
const busy = computed(() => !!props.mutation)

function modelCount(provider: LlmProvider) {
  if (provider.id === null) return 1
  return props.models.filter((item) => item.provider_id === provider.id).length
}

function resetProviderForm() {
  connectionName.value = ''
  baseUrl.value = ''
  firstModel.value = ''
  apiKey.value = ''
  addingProvider.value = false
}

function resetModelForm() {
  modelLabel.value = ''
  modelId.value = ''
  modelCapabilities.text_chat = true
  modelCapabilities.structured_output = true
  modelCapabilities.streaming = true
  modelCapabilities.vision = false
  modelCapabilities.embeddings = false
  addingModel.value = false
}

async function submitProvider() {
  if (!providerValid.value) return
  const saved = await props.createProvider({
    name: connectionName.value.trim(),
    base_url: baseUrl.value.trim(),
    model: firstModel.value.trim(),
    api_key: apiKey.value.trim(),
  })
  if (!saved) return
  resetProviderForm()
  selectedKey.value = providerKey(saved)
}

async function submitModel() {
  const provider = selectedProvider.value
  if (!modelValid.value || provider?.id === null || provider?.id === undefined) return
  const saved = await props.createModel(provider.id, {
    label: modelLabel.value.trim(),
    model: modelId.value.trim(),
    capabilities: { ...modelCapabilities },
    runtime_policy: {},
  })
  if (saved) resetModelForm()
}

onBeforeUnmount(() => {
  apiKey.value = ''
})
</script>

<template>
  <div class="connections-layout">
    <aside class="connection-sidebar" aria-label="API 连接列表">
      <div class="connection-sidebar-heading">
        <div>
          <h2>API 连接</h2>
          <p>一套接口地址和密钥</p>
        </div>
        <button
          type="button"
          class="add-icon"
          aria-label="添加 API 连接"
          :disabled="busy"
          @click="addingProvider = true"
        >
          +
        </button>
      </div>

      <div v-if="providers.length" class="connection-list">
        <button
          v-for="provider in providers"
          :key="providerKey(provider)"
          type="button"
          class="connection-item"
          :class="{ selected: selectedKey === providerKey(provider) }"
          @click="selectedKey = providerKey(provider); addingProvider = false"
        >
          <span class="connection-dot" :class="{ active: provider.is_active }" />
          <span>
            <strong>{{ provider.name }}</strong>
            <small>{{ modelCount(provider) }} 个模型</small>
          </span>
          <span v-if="provider.source === 'environment'" class="read-only">只读</span>
          <span v-else-if="provider.is_active" class="read-only">兼容默认</span>
        </button>
      </div>
      <div v-else class="connection-empty">
        <p>还没有连接</p>
        <small>先添加一套可用的 API。</small>
      </div>

      <button
        type="button"
        class="add-connection"
        :disabled="busy"
        @click="addingProvider = true"
      >
        <AppIcon name="plus" />添加连接
      </button>
    </aside>

    <main class="connection-main">
      <form v-if="addingProvider" class="editor-card provider-editor" @submit.prevent="submitProvider">
        <div class="section-heading">
          <div>
            <p class="eyebrow">新的 API 连接</p>
            <h2>连接一个模型服务</h2>
            <p>首版支持 OpenAI 兼容格式；其他接口格式需要对应适配器。</p>
          </div>
          <button type="button" class="icon-button" aria-label="取消添加连接" @click="resetProviderForm">
            <AppIcon name="close" />
          </button>
        </div>
        <div class="provider-fields">
          <label>
            <span>连接名称</span>
            <input v-model="connectionName" required maxlength="120" placeholder="例如：NUS 学校 API" />
            <small>只用于帮助你辨认。</small>
          </label>
          <label>
            <span>接口地址（Base URL）</span>
            <input
              v-model="baseUrl"
              required
              type="url"
              maxlength="1000"
              autocomplete="url"
              placeholder="https://example.edu/v1"
            />
          </label>
          <label>
            <span>第一个模型 ID</span>
            <input v-model="firstModel" required maxlength="300" placeholder="例如：qwen3.5:27b" />
            <small>填写服务方文档中的准确名称。</small>
          </label>
          <label>
            <span>API Key</span>
            <input
              v-model="apiKey"
              required
              type="password"
              maxlength="4000"
              autocomplete="new-password"
              placeholder="只写入，不回显"
            />
          </label>
        </div>
        <div class="editor-footer">
          <p>密钥只发送到后端并存入系统钥匙串，不会从读取接口传回页面。</p>
          <button class="button primary" :disabled="!providerValid || busy">
            <span v-if="mutation === 'provider'" class="spinner" />
            {{ mutation === 'provider' ? '正在保存' : '保存连接' }}
          </button>
        </div>
      </form>

      <template v-else-if="selectedProvider">
        <header class="provider-heading">
          <div>
            <div class="provider-title-line">
              <h2>{{ selectedProvider.name }}</h2>
              <span>{{ selectedProvider.source === 'environment' ? '.env 配置' : '已保存连接' }}</span>
            </div>
            <p>{{ selectedProvider.base_url }}</p>
          </div>
          <span class="key-state">
            <span class="connection-dot active" />{{ selectedProvider.has_api_key ? '密钥已设置' : '缺少密钥' }}
          </span>
        </header>

        <div v-if="selectedProvider.source === 'environment'" class="environment-note">
          <AppIcon name="info" />
          <p>
            当前模型：{{ selectedProvider.model }}。<br />
            这是项目根目录里的只读配置，可继续作为兼容默认。若要给不同工作分配不同模型，请添加一个可管理的连接。
          </p>
        </div>

        <template v-else>
          <section class="models-section">
            <div class="section-heading compact">
              <div>
                <h3>这个连接下的模型</h3>
                <p>同一套地址和密钥可以添加多个模型 ID。</p>
              </div>
              <button
                type="button"
                class="button secondary small"
                :disabled="busy"
                @click="addingModel = !addingModel"
              >
                {{ addingModel ? '取消' : '添加模型' }}
              </button>
            </div>

            <form v-if="addingModel" class="model-editor" @submit.prevent="submitModel">
              <div class="model-editor-fields">
                <label>
                  <span>显示名称</span>
                  <input v-model="modelLabel" required maxlength="120" placeholder="例如：快速文字模型" />
                </label>
                <label>
                  <span>模型 ID</span>
                  <input v-model="modelId" required maxlength="300" placeholder="服务方提供的准确名称" />
                </label>
              </div>
              <fieldset>
                <legend>这个模型预计能做什么？</legend>
                <label v-for="item in CAPABILITIES" :key="item.key" :title="item.description">
                  <input v-model="modelCapabilities[item.key]" type="checkbox" />{{ item.name }}
                </label>
              </fieldset>
              <div class="model-editor-footer">
                <p>这里只是声明；真实验证会发出短请求，可能产生少量调用费用。</p>
                <button class="button primary small" :disabled="!modelValid || busy">
                  <span v-if="mutation.startsWith('create-model:')" class="spinner" />保存模型
                </button>
              </div>
            </form>

            <div v-if="selectedModels.length" class="model-list">
              <ModelCard
                v-for="item in selectedModels"
                :key="item.id"
                :model="item"
                :busy="busy"
                :save-capabilities="saveCapabilities"
                :verify-model="verifyModel"
              />
            </div>
            <div v-else class="models-empty">这个连接还没有模型。</div>
          </section>
        </template>
      </template>

      <div v-else class="main-empty">
        <p>选择一个连接查看模型，或者添加新连接。</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.connections-layout {
  display: grid;
  min-height: 0;
  height: 100%;
  grid-template-columns: 238px minmax(0, 1fr);
}
.connection-sidebar {
  display: flex;
  min-height: 0;
  flex-direction: column;
  border-right: 1px solid var(--line);
  background: #f7f9fb;
  padding: 20px 15px;
}
.connection-sidebar-heading,
.section-heading,
.provider-heading,
.provider-title-line,
.editor-footer,
.model-editor-footer,
.key-state {
  display: flex;
  align-items: center;
}
.connection-sidebar-heading,
.section-heading,
.provider-heading,
.editor-footer,
.model-editor-footer {
  justify-content: space-between;
  gap: 16px;
}
.connection-sidebar-heading {
  padding: 0 5px 14px;
}
.connection-sidebar-heading h2,
.section-heading h2,
.provider-heading h2 {
  margin: 0;
  font-size: 14px;
}
.connection-sidebar-heading p,
.section-heading p,
.provider-heading p,
.editor-footer p,
.model-editor-footer p {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
}
.connection-sidebar-heading p {
  margin-top: 3px;
}
.add-icon {
  display: grid;
  width: 27px;
  height: 27px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #fff;
  color: var(--accent);
}
.connection-list {
  display: grid;
  min-height: 0;
  gap: 5px;
  overflow-y: auto;
}
.connection-item {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 9px;
  padding: 10px 9px;
  background: transparent;
  color: var(--body);
  text-align: left;
}
.connection-item:hover,
.connection-item.selected {
  border-color: #dfe7ed;
  background: #fff;
}
.connection-item > span:nth-child(2) {
  min-width: 0;
  flex: 1;
}
.connection-item strong,
.connection-item small {
  display: block;
}
.connection-item strong {
  overflow: hidden;
  font-size: 11px;
  font-weight: 520;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.connection-item small,
.read-only {
  margin-top: 3px;
  color: var(--muted);
  font-size: 9px;
}
.read-only {
  flex-shrink: 0;
  margin: 0;
}
.connection-dot {
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #bdc7ce;
}
.connection-dot.active {
  background: #67917c;
}
.add-connection {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: auto;
  padding: 13px 8px 3px;
  border: 0;
  border-top: 1px solid var(--line);
  background: transparent;
  color: var(--accent);
  font-size: 10px;
}
.add-connection .app-icon {
  width: 13px;
  height: 13px;
}
.connection-empty,
.main-empty,
.models-empty {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}
.connection-empty {
  padding: 28px 8px;
}
.connection-main {
  min-width: 0;
  overflow-y: auto;
  padding: 25px 28px 30px;
  background: linear-gradient(145deg, #fff, #fbfcfd);
}
.provider-heading {
  align-items: flex-start;
  padding-bottom: 21px;
  border-bottom: 1px solid var(--line);
}
.provider-title-line {
  gap: 9px;
}
.provider-title-line span {
  padding: 3px 6px;
  border: 1px solid var(--line);
  border-radius: 5px;
  background: var(--soft);
  color: var(--muted);
  font-size: 9px;
}
.provider-heading p {
  max-width: 560px;
  margin-top: 6px;
  overflow-wrap: anywhere;
}
.key-state {
  flex-shrink: 0;
  gap: 6px;
  color: var(--muted);
  font-size: 10px;
}
.environment-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 20px;
  padding: 14px;
  border: 1px solid #dfe8ee;
  border-radius: 9px;
  background: #f3f7fa;
  color: var(--body);
  font-size: 11px;
  line-height: 1.8;
}
.environment-note .app-icon {
  width: 15px;
  height: 15px;
  color: var(--accent);
}
.models-section {
  padding-top: 21px;
}
.section-heading {
  align-items: flex-start;
}
.section-heading h3 {
  margin: 0;
  font-size: 13px;
}
.section-heading p {
  margin-top: 5px;
}
.editor-card,
.model-editor {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
}
.editor-card {
  padding: 20px;
}
.section-heading .eyebrow {
  margin: 0 0 5px;
}
.provider-fields,
.model-editor-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;
}
.provider-fields {
  margin-top: 20px;
}
.provider-fields label > span,
.model-editor-fields label > span {
  display: block;
  margin-bottom: 6px;
  color: var(--body);
  font-size: 10px;
}
.provider-fields input,
.model-editor-fields input {
  padding: 9px 11px;
  font-size: 12px;
}
.provider-fields small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 9px;
}
.editor-footer {
  align-items: flex-end;
  margin-top: 20px;
  border-top: 1px solid var(--line);
  padding-top: 15px;
}
.editor-footer p {
  max-width: 470px;
}
.model-editor {
  margin: 15px 0;
  padding: 14px;
  background: #f9fbfc;
}
.model-editor fieldset {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 14px 0;
  border: 0;
  padding: 0;
}
.model-editor legend {
  width: 100%;
  margin-bottom: 8px;
  color: var(--body);
  font-size: 10px;
}
.model-editor fieldset label {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--body);
  font-size: 10px;
}
.model-editor input[type='checkbox'] {
  width: auto;
  margin: 0;
  padding: 0;
}
.model-list {
  display: grid;
  gap: 9px;
  margin-top: 15px;
}
.models-empty {
  padding: 35px 5px;
  text-align: center;
}
.main-empty {
  display: grid;
  min-height: 300px;
  place-items: center;
}
@media (max-width: 760px) {
  .connections-layout {
    grid-template-columns: 1fr;
  }
  .connection-sidebar {
    max-height: 190px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .connection-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .connection-main {
    padding: 20px 18px;
  }
}
@media (max-width: 560px) {
  .provider-fields,
  .model-editor-fields {
    grid-template-columns: 1fr;
  }
  .provider-heading,
  .editor-footer,
  .model-editor-footer {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
