import { computed, reactive, ref } from 'vue'
import { errorMessage } from '../../shared/api'
import { modelSettingsApi } from './api'
import type {
  CapabilityName,
  LlmProviderInput,
  ModelCapabilityDeclaration,
  ModelConfig,
  ModelConfigInput,
  RoleBinding,
  RoleDefinition,
  RoleResolutionState,
  SettingsScope,
} from './types'

export function useModelSettings() {
  const providers = ref<Awaited<ReturnType<typeof modelSettingsApi.listProviders>>>([])
  const models = ref<ModelConfig[]>([])
  const roles = ref<RoleDefinition[]>([])
  const bindings = ref<RoleBinding[]>([])
  const resolutions = reactive<Record<string, RoleResolutionState>>({})
  const scope = ref<SettingsScope>({ type: 'global', id: null })
  const loading = ref(false)
  const loadingRoutes = ref(false)
  const mutation = ref('')
  const error = ref('')
  const notice = ref('')
  let routeLoadVersion = 0

  const busy = computed(() => loading.value || !!mutation.value)

  async function refreshConnections() {
    const [nextProviders, nextModels] = await Promise.all([
      modelSettingsApi.listProviders(),
      modelSettingsApi.listModels(),
    ])
    providers.value = nextProviders
    models.value = nextModels
  }

  async function loadRoutes() {
    const version = ++routeLoadVersion
    loadingRoutes.value = true
    bindings.value = []
    for (const key of Object.keys(resolutions)) delete resolutions[key]
    const current = scope.value
    try {
      const [nextBindings, nextResolutions] = await Promise.all([
        modelSettingsApi.listBindings(current.type, current.id),
        Promise.all(
          roles.value.map(async (role) => {
            try {
              return [
                role.key,
                {
                  value: await modelSettingsApi.resolveRole(role.key, current.type, current.id),
                  error: '',
                },
              ] as const
            } catch (cause) {
              return [
                role.key,
                { value: null, error: errorMessage(cause) },
              ] as const
            }
          }),
        ),
      ])
      if (version !== routeLoadVersion) return
      bindings.value = nextBindings
      for (const key of Object.keys(resolutions)) delete resolutions[key]
      for (const [key, state] of nextResolutions) resolutions[key] = state
    } catch (cause) {
      if (version === routeLoadVersion) error.value = errorMessage(cause)
    } finally {
      if (version === routeLoadVersion) loadingRoutes.value = false
    }
  }

  async function load(initialScope?: SettingsScope) {
    if (loading.value) return
    if (initialScope) scope.value = initialScope
    loading.value = true
    error.value = ''
    notice.value = ''
    try {
      const [nextProviders, nextModels, nextRoles] = await Promise.all([
        modelSettingsApi.listProviders(),
        modelSettingsApi.listModels(),
        modelSettingsApi.listRoles(),
      ])
      providers.value = nextProviders
      models.value = nextModels
      roles.value = nextRoles
      await loadRoutes()
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function changeScope(next: SettingsScope) {
    if (mutation.value) return
    if (scope.value.type === next.type && scope.value.id === next.id) return
    scope.value = next
    error.value = ''
    notice.value = ''
    await loadRoutes()
  }

  async function createProvider(input: Omit<LlmProviderInput, 'activate'>) {
    if (mutation.value) return null
    mutation.value = 'provider'
    error.value = ''
    notice.value = ''
    try {
      // 新连接不会偷偷替换职责；用户在“职责分配”中明确选择后才生效。
      const saved = await modelSettingsApi.createProvider({ ...input, activate: false })
      await refreshConnections()
      notice.value = `已保存连接“${saved.name}”，并建立首个模型。`
      return saved
    } catch (cause) {
      error.value = errorMessage(cause)
      return null
    } finally {
      mutation.value = ''
    }
  }

  async function createModel(providerId: number, input: ModelConfigInput) {
    if (mutation.value) return false
    mutation.value = `create-model:${providerId}`
    error.value = ''
    notice.value = ''
    try {
      await modelSettingsApi.createModel(providerId, input)
      await refreshConnections()
      notice.value = `已添加模型“${input.label}”。能力仍需通过真实测试确认。`
      return true
    } catch (cause) {
      error.value = errorMessage(cause)
      return false
    } finally {
      mutation.value = ''
    }
  }

  async function saveCapabilities(model: ModelConfig, capabilities: ModelCapabilityDeclaration) {
    if (mutation.value) return false
    mutation.value = `model:${model.id}`
    error.value = ''
    notice.value = ''
    try {
      await modelSettingsApi.updateModel(model.id, {
        expected_revision: model.revision,
        capabilities,
      })
      await refreshConnections()
      await loadRoutes()
      notice.value = `已保存“${model.label}”的能力声明。`
      return true
    } catch (cause) {
      error.value = errorMessage(cause)
      await refreshConnections().catch(() => undefined)
      return false
    } finally {
      mutation.value = ''
    }
  }

  async function verifyModel(model: ModelConfig, capabilities: CapabilityName[]) {
    if (mutation.value || !capabilities.length) return false
    mutation.value = `verify:${model.id}`
    error.value = ''
    notice.value = ''
    try {
      await modelSettingsApi.verifyModel(model.id, model.revision, capabilities)
      await refreshConnections()
      await loadRoutes()
      notice.value = `已完成“${model.label}”的能力测试。`
      return true
    } catch (cause) {
      error.value = errorMessage(cause)
      await refreshConnections().catch(() => undefined)
      return false
    } finally {
      mutation.value = ''
    }
  }

  async function setBinding(role: RoleDefinition, modelId: number | null) {
    if (mutation.value || loadingRoutes.value) return
    const current = bindings.value.find((item) => item.role_key === role.key)
    if ((current?.model_config_id ?? null) === modelId) return
    mutation.value = `role:${role.key}`
    error.value = ''
    notice.value = ''
    try {
      if (modelId === null) {
        if (current) {
          await modelSettingsApi.deleteBinding(
            role.key,
            scope.value.type,
            scope.value.id,
            current.revision,
          )
        }
      } else {
        await modelSettingsApi.putBinding(role.key, {
          scope_type: scope.value.type,
          ...(scope.value.id ? { scope_id: scope.value.id } : {}),
          model_config_id: modelId,
          expected_revision: current?.revision ?? 0,
        })
      }
      await loadRoutes()
      notice.value = modelId === null ? `“${role.name}”已恢复继承。` : `“${role.name}”已更新。`
    } catch (cause) {
      error.value = errorMessage(cause)
      await loadRoutes()
    } finally {
      mutation.value = ''
    }
  }

  return {
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
    loadRoutes,
    changeScope,
    createProvider,
    createModel,
    saveCapabilities,
    verifyModel,
    setBinding,
  }
}
