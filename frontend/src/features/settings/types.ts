export type ProviderSource = 'saved' | 'environment'

export type LlmProvider = {
  id: number | null
  name: string
  base_url: string
  model: string
  is_active: boolean
  source: ProviderSource
  has_api_key: boolean
}

export type LlmProviderInput = {
  name: string
  base_url: string
  model: string
  api_key: string
  activate: boolean
}

export type CapabilityName =
  | 'text_chat'
  | 'structured_output'
  | 'streaming'
  | 'vision'
  | 'embeddings'

export type CapabilityVerificationStatus =
  | 'unsupported'
  | 'unverified'
  | 'verified'
  | 'failed'

export type CapabilityState = {
  supported: boolean
  status: CapabilityVerificationStatus
  checked_at: string | null
  error_code: string | null
}

export type ModelCapabilityDeclaration = Record<CapabilityName, boolean>
export type ModelCapabilityStatus = Record<CapabilityName, CapabilityState>

export type ModelRuntimePolicy = {
  temperature?: number | null
  max_output_tokens?: number | null
  request_timeout_seconds?: number | null
  max_retries?: number | null
}

export type ModelConfig = {
  id: number
  provider_id: number
  label: string
  model: string
  capabilities: ModelCapabilityStatus
  runtime_policy: ModelRuntimePolicy
  is_enabled: boolean
  revision: number
  created_at: string
  updated_at: string
}

export type ModelConfigInput = {
  label: string
  model: string
  capabilities: ModelCapabilityDeclaration
  runtime_policy?: ModelRuntimePolicy
}

export type ModelConfigUpdate = {
  expected_revision: number
  label?: string
  model?: string
  capabilities?: ModelCapabilityDeclaration
  runtime_policy?: ModelRuntimePolicy
  is_enabled?: boolean
}

export type ScopeType = 'global' | 'course' | 'intake' | 'directory_draft'

export type RoleDefinition = {
  key: string
  name: string
  description: string
  required_capabilities: CapabilityName[]
  default_role: string
}

export type RoleBinding = {
  id: number
  scope_type: ScopeType
  scope_id: string | null
  role_key: string
  model_config_id: number
  revision: number
  model: ModelConfig
}

export type ResolvedRole = {
  requested_role: string
  requested_scope_type: ScopeType
  requested_scope_id: string | null
  resolution_source: string
  binding_id: number | null
  provider_id: number | null
  provider_name: string
  base_url: string
  model_config_id: number | null
  model: string
  model_revision: number | null
  runtime_policy: ModelRuntimePolicy
  config_fingerprint: string
  required_capabilities: CapabilityName[]
  capabilities: ModelCapabilityStatus | null
}

export type SettingsScope = {
  type: 'global' | 'course'
  id: string | null
}

export type RoleResolutionState = {
  value: ResolvedRole | null
  error: string
}
