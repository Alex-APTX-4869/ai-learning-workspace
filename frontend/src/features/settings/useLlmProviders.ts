import { computed, ref } from 'vue'
import { errorMessage } from '../../shared/api'
import { llmProvidersApi } from './api'
import type { LlmProvider } from './types'

export function useLlmProviders() {
  const providers = ref<LlmProvider[]>([])
  const active = ref<LlmProvider | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const activatingId = ref<number | null>(null)
  const switchingEnvironment = ref(false)
  const error = ref('')
  const notice = ref('')
  const busy = computed(
    () =>
      loading.value || saving.value || activatingId.value !== null || switchingEnvironment.value,
  )

  async function load() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    try {
      const [saved, current] = await Promise.all([
        llmProvidersApi.list(),
        llmProvidersApi.active(),
      ])
      providers.value = saved
      active.value = current
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function save(input: {
    name: string
    base_url: string
    model: string
    api_key: string
  }) {
    if (saving.value) return false
    saving.value = true
    error.value = ''
    notice.value = ''
    try {
      const saved = await llmProvidersApi.create({ ...input, activate: true })
      const index = providers.value.findIndex((provider) => provider.id === saved.id)
      providers.value = providers.value.map((provider) => ({ ...provider, is_active: false }))
      if (index < 0) providers.value.unshift(saved)
      else providers.value[index] = saved
      active.value = saved
      notice.value = '配置已安全保存，并设为当前使用。'
      return true
    } catch (cause) {
      error.value = errorMessage(cause)
      return false
    } finally {
      saving.value = false
    }
  }

  async function activate(provider: LlmProvider) {
    if (provider.id === null || activatingId.value !== null) return
    activatingId.value = provider.id
    error.value = ''
    notice.value = ''
    try {
      const selected = await llmProvidersApi.activate(provider.id)
      providers.value = providers.value.map((item) => ({
        ...item,
        is_active: item.id === selected.id,
      }))
      active.value = selected
      notice.value = `已切换到 ${selected.name}。`
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      activatingId.value = null
    }
  }

  async function activateEnvironment() {
    if (busy.value) return
    switchingEnvironment.value = true
    error.value = ''
    notice.value = ''
    try {
      const selected = await llmProvidersApi.activateEnvironment()
      providers.value = providers.value.map((item) => ({
        ...item,
        is_active: item.source === 'environment',
      }))
      active.value = selected
      notice.value = '已切换回 .env 中的模型配置。'
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      switchingEnvironment.value = false
    }
  }

  return {
    providers,
    active,
    loading,
    saving,
    activatingId,
    switchingEnvironment,
    busy,
    error,
    notice,
    load,
    save,
    activate,
    activateEnvironment,
  }
}
