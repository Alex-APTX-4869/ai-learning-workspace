<script setup lang="ts">
import { computed } from 'vue'
import type { CourseSummary } from '../../courses/types'
import {
  ADVANCED_ROLE_GROUPS,
  BASIC_ROLE_KEYS,
  DOCUMENT_ROLE_KEY,
  rolesInGroup,
} from '../modelCatalog'
import type {
  LlmProvider,
  ModelConfig,
  RoleBinding,
  RoleDefinition,
  RoleResolutionState,
  SettingsScope,
} from '../types'
import RoleAssignmentRow from './RoleAssignmentRow.vue'
import DocumentRecognitionSettings from './DocumentRecognitionSettings.vue'

const props = defineProps<{
  courses: CourseSummary[]
  scope: SettingsScope
  providers: LlmProvider[]
  models: ModelConfig[]
  roles: RoleDefinition[]
  bindings: RoleBinding[]
  resolutions: Record<string, RoleResolutionState>
  loadingRoutes: boolean
  mutation: string
}>()
const emit = defineEmits<{
  changeScope: [scope: SettingsScope]
  changeBinding: [role: RoleDefinition, modelId: number | null]
  showConnections: []
}>()

const scopeValue = computed(() =>
  props.scope.type === 'global' ? 'global' : `course:${props.scope.id}`,
)
const basicRoles = computed(() =>
  BASIC_ROLE_KEYS.map((key) => props.roles.find((role) => role.key === key)).filter(
    (role): role is RoleDefinition => !!role,
  ),
)
const documentRole = computed(() => props.roles.find(role => role.key === DOCUMENT_ROLE_KEY))
const advancedOverrideCount = computed(() =>
  props.bindings.filter(
    (binding) =>
      !BASIC_ROLE_KEYS.includes(binding.role_key as (typeof BASIC_ROLE_KEYS)[number]) && binding.role_key !== DOCUMENT_ROLE_KEY,
  ).length,
)

function bindingFor(role: RoleDefinition) {
  return props.bindings.find((binding) => binding.role_key === role.key)
}

function changeScope(event: Event) {
  const raw = (event.target as HTMLSelectElement).value
  if (raw === 'global') emit('changeScope', { type: 'global', id: null })
  else emit('changeScope', { type: 'course', id: raw.slice('course:'.length) })
}

function changeBinding(role: RoleDefinition, modelId: number | null) {
  emit('changeBinding', role, modelId)
}
</script>

<template>
  <div class="routes-panel">
    <header class="routes-heading">
      <div>
        <p class="eyebrow">职责分配</p>
        <h2>决定每类 AI 工作使用哪个模型</h2>
        <p>修改只影响之后开始的任务；正在运行的任务继续使用开始时的配置。</p>
      </div>
      <label class="scope-picker">
        <span>设置范围</span>
        <select :value="scopeValue" :disabled="!!mutation" @change="changeScope">
          <option value="global">全局默认 · 所有课程</option>
          <option v-for="course in courses" :key="course.id" :value="`course:${course.id}`">
            课程 · {{ course.name }}
          </option>
        </select>
      </label>
    </header>

    <div v-if="!models.length" class="no-models">
      <div>
        <h3>还没有可分配的模型</h3>
        <p>先添加一个可管理的 API 连接和模型，再回来决定各项工作由谁完成。</p>
      </div>
      <button type="button" class="button secondary small" @click="emit('showConnections')">
        前往连接与模型
      </button>
    </div>

    <section class="basic-routes" aria-labelledby="basic-routes-title">
        <div class="section-copy">
          <h3 id="basic-routes-title">基础设置</h3>
          <p>多数情况下只设置这三项即可。未单独指定的工作会沿用对应默认模型。</p>
        </div>
        <div class="route-list" :class="{ refreshing: loadingRoutes }">
          <RoleAssignmentRow
            v-for="role in basicRoles"
            :key="role.key"
            prominent
            :role="role"
            :scope="scope"
            :providers="providers"
            :models="models"
            :binding="bindingFor(role)"
            :resolution="resolutions[role.key]"
            :mutation="mutation"
            :loading="loadingRoutes"
            @change="changeBinding"
          />
        </div>
    </section>

    <DocumentRecognitionSettings v-if="documentRole" :role="documentRole" :scope="scope" :providers="providers"
      :models="models" :binding="bindingFor(documentRole)" :resolution="resolutions[documentRole.key]"
      :mutation="mutation" :loading="loadingRoutes" @change="changeBinding" @show-connections="emit('showConnections')" />

    <details class="advanced-routes">
        <summary>
          <span>
            <strong>高级职责分配</strong>
            <small>仅在你希望某个步骤使用不同模型时设置</small>
          </span>
          <span>{{ advancedOverrideCount ? `${advancedOverrideCount} 项单独设置` : '全部继承' }}</span>
        </summary>
        <div class="advanced-body">
          <section
            v-for="group in ADVANCED_ROLE_GROUPS"
            :key="group.id"
            class="role-group"
          >
            <h3>{{ group.name }}</h3>
            <div class="route-list" :class="{ refreshing: loadingRoutes }">
              <RoleAssignmentRow
                v-for="role in rolesInGroup(roles, group.prefixes)"
                :key="role.key"
                :role="role"
                :scope="scope"
                :providers="providers"
                :models="models"
                :binding="bindingFor(role)"
                :resolution="resolutions[role.key]"
                :mutation="mutation"
                :loading="loadingRoutes"
                @change="changeBinding"
              />
            </div>
          </section>
        </div>
    </details>
  </div>
</template>

<style scoped>
.routes-panel {
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  padding: 25px 29px 32px;
  background: linear-gradient(145deg, #fff, #fafcfd);
}
.routes-heading,
.no-models {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 22px;
}
.routes-heading {
  padding-bottom: 21px;
  border-bottom: 1px solid var(--line);
}
.routes-heading h2 {
  margin: 5px 0 6px;
  font-size: 16px;
}
.routes-heading > div > p:last-child,
.section-copy p,
.no-models p {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
}
.scope-picker {
  width: min(280px, 38%);
  flex-shrink: 0;
}
.scope-picker > span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 9px;
}
.scope-picker select {
  width: 100%;
  border: 1px solid #dce4eb;
  border-radius: 8px;
  background: #fbfcfd;
  padding: 9px 10px;
  font-size: 11px;
}
.no-models {
  align-items: center;
  margin-top: 22px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--soft);
}
.no-models h3,
.section-copy h3,
.role-group h3 {
  margin: 0;
  font-size: 12px;
}
.no-models p,
.section-copy p {
  margin-top: 5px;
}
.basic-routes {
  padding-top: 22px;
}
.section-copy {
  margin-bottom: 11px;
}
.route-list {
  display: grid;
  gap: 8px;
  transition: opacity 0.15s;
}
.route-list.refreshing {
  opacity: 0.68;
}
.advanced-routes {
  margin-top: 20px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #f9fbfc;
}
.advanced-routes > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 15px 17px;
  cursor: pointer;
  list-style: none;
}
.advanced-routes > summary::-webkit-details-marker {
  display: none;
}
.advanced-routes > summary span:first-child,
.advanced-routes > summary strong,
.advanced-routes > summary small {
  display: block;
}
.advanced-routes > summary strong {
  font-size: 11px;
  font-weight: 550;
}
.advanced-routes > summary small,
.advanced-routes > summary > span:last-child {
  margin-top: 4px;
  color: var(--muted);
  font-size: 9px;
}
.advanced-body {
  display: grid;
  gap: 22px;
  border-top: 1px solid var(--line);
  padding: 19px 17px 22px;
}
.role-group h3 {
  margin-bottom: 9px;
  color: #657887;
  font-size: 10px;
  letter-spacing: 0.5px;
}
@media (max-width: 700px) {
  .routes-panel {
    padding: 21px 18px;
  }
  .routes-heading,
  .no-models {
    align-items: stretch;
    flex-direction: column;
  }
  .scope-picker {
    width: 100%;
  }
}
</style>
