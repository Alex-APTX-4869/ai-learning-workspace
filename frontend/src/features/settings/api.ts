import { apiUrl, httpErrorFromResponse, request } from '../../shared/api'
import type {
  CapabilityName,
  LlmProvider,
  LlmProviderInput,
  ModelConfig,
  ModelConfigInput,
  ModelConfigUpdate,
  ResolvedRole,
  RoleBinding,
  RoleDefinition,
  ScopeType,
} from './types'

function scopeQuery(scopeType: ScopeType, scopeId: string | null) {
  const query = new URLSearchParams({ scope_type: scopeType })
  if (scopeId) query.set('scope_id', scopeId)
  return query.toString()
}

async function requestNoContent(path: string, options: RequestInit) {
  let response: Response
  try {
    response = await fetch(apiUrl(path), options)
  } catch {
    throw new Error('暂时无法连接后端，请确认服务已启动后重试。')
  }
  if (!response.ok) throw await httpErrorFromResponse(response)
}

export const modelSettingsApi = {
  listProviders: () => request<LlmProvider[]>('/llm-providers'),
  createProvider: (input: LlmProviderInput) =>
    request<LlmProvider>('/llm-providers', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  listModels: () => request<ModelConfig[]>('/llm-models'),
  listProviderModels: (providerId: number) =>
    request<ModelConfig[]>(`/llm-providers/${providerId}/models`),
  createModel: (providerId: number, input: ModelConfigInput) =>
    request<ModelConfig>(`/llm-providers/${providerId}/models`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  updateModel: (modelId: number, input: ModelConfigUpdate) =>
    request<ModelConfig>(`/llm-models/${modelId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    }),
  verifyModel: (
    modelId: number,
    expectedRevision: number,
    capabilities: CapabilityName[],
  ) =>
    request<ModelConfig>(`/llm-models/${modelId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ expected_revision: expectedRevision, capabilities }),
    }),
  listRoles: () => request<RoleDefinition[]>('/llm-roles'),
  listBindings: (scopeType: ScopeType, scopeId: string | null) =>
    request<RoleBinding[]>(`/llm-role-bindings?${scopeQuery(scopeType, scopeId)}`),
  resolveRole: (role: string, scopeType: ScopeType, scopeId: string | null) =>
    request<ResolvedRole>(
      `/llm-role-routing/${encodeURIComponent(role)}?${scopeQuery(scopeType, scopeId)}`,
    ),
  putBinding: (
    role: string,
    input: {
      scope_type: ScopeType
      scope_id?: string
      model_config_id: number
      expected_revision: number
    },
  ) =>
    request<RoleBinding>(`/llm-role-bindings/${encodeURIComponent(role)}`, {
      method: 'PUT',
      body: JSON.stringify(input),
    }),
  deleteBinding: (
    role: string,
    scopeType: ScopeType,
    scopeId: string | null,
    expectedRevision: number,
  ) => {
    const query = new URLSearchParams({
      scope_type: scopeType,
      expected_revision: String(expectedRevision),
    })
    if (scopeId) query.set('scope_id', scopeId)
    return requestNoContent(
      `/llm-role-bindings/${encodeURIComponent(role)}?${query.toString()}`,
      { method: 'DELETE' },
    )
  },
}

// 旧名字暂时保留，避免尚未迁移的调用方在同一开发阶段中断。
export const llmProvidersApi = {
  list: modelSettingsApi.listProviders,
  active: () => request<LlmProvider>('/llm-providers/active'),
  create: modelSettingsApi.createProvider,
  activate: (id: number) =>
    request<LlmProvider>(`/llm-providers/${id}/activate`, { method: 'POST' }),
  activateEnvironment: () =>
    request<LlmProvider>('/llm-providers/environment/activate', { method: 'POST' }),
}
