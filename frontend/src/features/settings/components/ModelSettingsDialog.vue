<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CourseSummary } from '../../courses/types'
import AppIcon from '../../../shared/components/AppIcon.vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import { useModelSettings } from '../useModelSettings'
import type { RoleDefinition, SettingsScope } from '../types'
import ConnectionsPanel from './ConnectionsPanel.vue'
import RoleAssignmentsPanel from './RoleAssignmentsPanel.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    currentCourseId?: number | null
    courses?: CourseSummary[]
  }>(),
  { currentCourseId: null, courses: () => [] },
)
const emit = defineEmits<{ close: [] }>()
const activeTab = ref<'connections' | 'roles'>('connections')
const {
  providers,
  models,
  roles,
  bindings,
  resolutions,
  scope,
  loading,
  loadingRoutes,
  mutation,
  busy,
  error,
  notice,
  load,
  changeScope,
  createProvider,
  createModel,
  saveCapabilities,
  verifyModel,
  setBinding,
} = useModelSettings()

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const initialScope: SettingsScope = props.currentCourseId
      ? { type: 'course', id: String(props.currentCourseId) }
      : { type: 'global', id: null }
    load(initialScope)
  },
  { immediate: true },
)

function changeBinding(role: RoleDefinition, modelId: number | null) {
  setBinding(role, modelId)
}
</script>

<template>
  <BaseDialog
    :open="open"
    wide
    labelledby="model-settings-title"
    :busy="busy"
    @close="emit('close')"
  >
    <!-- v-if 会在关闭时销毁表单，确保未提交的 API Key 不继续留在页面内存中。 -->
    <div v-if="open" class="settings-shell">
      <header class="settings-header">
        <div class="settings-title">
          <p class="eyebrow">连接、能力与职责</p>
          <h1 id="model-settings-title">模型与 API</h1>
        </div>
        <nav aria-label="模型设置页面">
          <button
            type="button"
            :aria-current="activeTab === 'connections' ? 'page' : undefined"
            @click="activeTab = 'connections'"
          >
            连接与模型
          </button>
          <button
            type="button"
            :aria-current="activeTab === 'roles' ? 'page' : undefined"
            @click="activeTab = 'roles'"
          >
            职责分配
          </button>
        </nav>
        <button
          type="button"
          class="icon-button close-button"
          aria-label="关闭模型与 API 设置"
          :disabled="busy"
          @click="emit('close')"
        >
          <AppIcon name="close" />
        </button>
      </header>

      <div v-if="loading" class="settings-loading" role="status">
        <span class="spinner" />
        <div>
          <strong>正在读取模型设置</strong>
          <p>连接、模型能力和职责会一起加载。</p>
        </div>
      </div>

      <div v-else class="settings-content">
        <ConnectionsPanel
          v-if="activeTab === 'connections'"
          :providers="providers"
          :models="models"
          :mutation="mutation"
          :create-provider="createProvider"
          :create-model="createModel"
          :save-capabilities="saveCapabilities"
          :verify-model="verifyModel"
        />
        <RoleAssignmentsPanel
          v-else
          :courses="courses"
          :scope="scope"
          :providers="providers"
          :models="models"
          :roles="roles"
          :bindings="bindings"
          :resolutions="resolutions"
          :loading-routes="loadingRoutes"
          :mutation="mutation"
          @change-scope="changeScope"
          @change-binding="changeBinding"
          @show-connections="activeTab = 'connections'"
        />
      </div>

      <div v-if="error || notice" class="settings-feedback" :class="{ failed: error }">
        <p role="status">{{ error || notice }}</p>
        <button
          v-if="error"
          type="button"
          class="feedback-action"
          :disabled="busy"
          @click="load(scope)"
        >
          重新读取
        </button>
      </div>
    </div>
  </BaseDialog>
</template>

<style scoped>
.settings-shell {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  background: #fff;
}
.settings-header {
  display: grid;
  flex-shrink: 0;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 20px;
  min-height: 75px;
  border-bottom: 1px solid var(--line);
  padding: 13px 25px 0;
  background: #ffffffed;
  backdrop-filter: blur(10px);
}
.settings-title {
  align-self: center;
  padding-bottom: 12px;
}
.settings-title h1 {
  margin-top: 4px;
  font-size: 17px;
}
nav {
  display: flex;
  height: 100%;
  align-items: flex-end;
  gap: 25px;
}
nav button {
  height: 100%;
  border: 0;
  border-bottom: 2px solid transparent;
  padding: 0 2px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
}
nav button[aria-current='page'] {
  border-bottom-color: var(--accent);
  color: var(--ink);
}
.close-button {
  justify-self: end;
  align-self: center;
  margin-bottom: 12px;
}
.settings-content {
  min-height: 0;
  flex: 1;
  overflow: hidden;
}
.settings-loading {
  display: flex;
  min-height: 0;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--muted);
}
.settings-loading strong {
  color: var(--body);
  font-size: 12px;
  font-weight: 500;
}
.settings-loading p {
  margin-top: 5px;
  font-size: 10px;
}
.settings-feedback {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 42px;
  border-top: 1px solid #dfe9ef;
  padding: 8px 24px;
  background: #f1f6f9;
  color: #526f85;
  font-size: 10px;
  line-height: 1.6;
}
.settings-feedback.failed {
  border-color: #edd8d7;
  background: #fdf5f4;
  color: var(--danger);
}
.feedback-action {
  flex-shrink: 0;
  border: 0;
  padding: 4px 0;
  background: transparent;
  color: inherit;
  font-size: 10px;
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (max-width: 620px) {
  .settings-header {
    grid-template-columns: 1fr auto;
    gap: 8px;
    padding-inline: 17px;
  }
  .settings-title {
    display: none;
  }
  nav {
    justify-self: start;
  }
  .close-button {
    grid-column: 2;
  }
}
</style>
