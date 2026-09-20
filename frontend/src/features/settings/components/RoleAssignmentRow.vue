<script setup lang="ts">
import { computed } from 'vue'
import {
  CAPABILITY_BY_KEY,
  modelCanHandle,
  modelMismatchReason,
  providerName,
  resolutionSourceLabel,
} from '../modelCatalog'
import type {
  LlmProvider,
  ModelConfig,
  RoleBinding,
  RoleDefinition,
  RoleResolutionState,
  SettingsScope,
} from '../types'

const props = defineProps<{
  role: RoleDefinition
  scope: SettingsScope
  providers: LlmProvider[]
  models: ModelConfig[]
  binding?: RoleBinding
  resolution?: RoleResolutionState
  mutation: string
  loading: boolean
  prominent?: boolean
}>()
const emit = defineEmits<{ change: [role: RoleDefinition, modelId: number | null] }>()

const compatibleCount = computed(
  () => props.models.filter((model) => modelCanHandle(model, props.role)).length,
)
const requiredText = computed(() =>
  props.role.required_capabilities.map((key) => CAPABILITY_BY_KEY[key].shortName).join('、'),
)
const inheritanceLabel = computed(() => {
  if (props.scope.type === 'course') return '继承上级设置'
  if (props.role.default_role !== props.role.key) {
    const defaultName =
      props.role.default_role === 'default.vision'
        ? '默认图片模型'
        : props.role.default_role === 'default.embedding'
          ? '默认向量模型'
          : '默认文字模型'
    return `继承${defaultName}`
  }
  return props.role.key === 'default.chat' ? '使用兼容默认' : '未设置'
})
const resolvedWarning = computed(() => {
  const resolved = props.resolution?.value
  if (!resolved?.capabilities) return ''
  const unverified = resolved.required_capabilities
    .filter((key) => resolved.capabilities?.[key].status === 'unverified')
    .map((key) => CAPABILITY_BY_KEY[key].shortName)
  return unverified.length ? `${unverified.join('、')}尚未独立验证` : ''
})

function change(event: Event) {
  const raw = (event.target as HTMLSelectElement).value
  emit('change', props.role, raw ? Number(raw) : null)
}
</script>

<template>
  <article class="role-row" :class="{ prominent }">
    <div class="role-copy">
      <div class="role-title-line">
        <h4>{{ role.name }}</h4>
        <span>需要：{{ requiredText }}</span>
      </div>
      <p>{{ role.description }}</p>
    </div>

    <div class="role-choice">
      <label :for="`role-${role.key}`">使用哪个模型</label>
      <select
        :id="`role-${role.key}`"
        :value="binding?.model_config_id ?? ''"
        :disabled="!!mutation || loading"
        @change="change"
      >
        <option value="">{{ inheritanceLabel }}</option>
        <option
          v-for="model in models"
          :key="model.id"
          :value="model.id"
          :disabled="!modelCanHandle(model, role)"
        >
          {{ providerName(providers, model.provider_id) }} · {{ model.label }}{{
            modelCanHandle(model, role) ? '' : `（${modelMismatchReason(model, role)}）`
          }}
        </option>
      </select>
      <small v-if="!compatibleCount && !resolution?.value">
        暂无能力匹配的模型；请到“连接与模型”声明能力并进行检测。
      </small>
    </div>

    <div class="effective-route" :class="{ failed: resolution?.error }">
      <span v-if="mutation === `role:${role.key}`" class="spinner" />
      <template v-else-if="resolution?.value">
        <strong>实际使用</strong>
        <span>{{ resolution.value.provider_name }} · {{ resolution.value.model }}</span>
        <small>{{ resolutionSourceLabel(resolution.value.resolution_source, role.key) }}</small>
        <small v-if="resolvedWarning" class="warning">{{ resolvedWarning }}</small>
      </template>
      <template v-else-if="resolution?.error">
        <strong>当前不可用</strong>
        <small>{{ resolution.error }}</small>
      </template>
      <template v-else>
        <span class="spinner" />正在确认生效模型…
      </template>
    </div>
  </article>
</template>

<style scoped>
.role-row {
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(210px, 0.9fr) minmax(210px, 0.9fr);
  gap: 18px;
  align-items: center;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}
.role-row.prominent {
  padding: 17px 18px;
  box-shadow: 0 2px 10px #34536d08;
}
.role-copy,
.role-choice,
.effective-route {
  min-width: 0;
}
.role-title-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
}
h4 {
  margin: 0;
  font-size: 12px;
  font-weight: 550;
}
.role-title-line span {
  color: #80909d;
  font-size: 8px;
}
.role-copy p {
  margin-top: 5px;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.6;
}
.role-choice label {
  display: block;
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 9px;
}
select {
  width: 100%;
  min-width: 0;
  border: 1px solid #dce4eb;
  border-radius: 8px;
  background: #fbfcfd;
  padding: 8px 9px;
  color: var(--body);
  font-size: 10px;
}
.role-choice > small {
  display: block;
  margin-top: 5px;
  color: #98703f;
  font-size: 9px;
}
.effective-route {
  display: grid;
  gap: 3px;
  border-left: 2px solid #d7e2e9;
  padding-left: 11px;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.45;
}
.effective-route strong {
  color: #718391;
  font-size: 8px;
  font-weight: 500;
  letter-spacing: 0.5px;
}
.effective-route span:not(.spinner) {
  overflow: hidden;
  color: var(--body);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.effective-route small {
  overflow-wrap: anywhere;
}
.effective-route .warning {
  color: #98703f;
}
.effective-route.failed {
  border-left-color: #e8c9c9;
  color: var(--danger);
}
@media (max-width: 920px) {
  .role-row {
    grid-template-columns: minmax(180px, 1fr) minmax(220px, 1fr);
  }
  .effective-route {
    grid-column: 1 / -1;
  }
}
@media (max-width: 620px) {
  .role-row {
    grid-template-columns: 1fr;
  }
  .effective-route {
    grid-column: auto;
  }
}
</style>
