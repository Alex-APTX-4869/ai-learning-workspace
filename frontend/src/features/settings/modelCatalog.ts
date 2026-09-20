import type {
  CapabilityName,
  CapabilityVerificationStatus,
  ModelConfig,
  RoleDefinition,
} from './types'

export const CAPABILITIES: Array<{
  key: CapabilityName
  name: string
  shortName: string
  description: string
}> = [
  {
    key: 'text_chat',
    name: '文字对话',
    shortName: '对话',
    description: '读取文字并生成回答。',
  },
  {
    key: 'structured_output',
    name: '结构化结果',
    shortName: '结构化',
    description: '按系统要求返回可以校验的数据结构。',
  },
  {
    key: 'streaming',
    name: '流式输出',
    shortName: '流式',
    description: '内容生成一部分就可以先显示一部分。',
  },
  {
    key: 'vision',
    name: '图片理解',
    shortName: '看图',
    description: '读取图片、公式截图和图表。',
  },
  {
    key: 'embeddings',
    name: '文本向量',
    shortName: '向量',
    description: '把文字转换成向量，用于从资料中查找相关内容；它不是聊天能力。',
  },
]

export const CAPABILITY_BY_KEY = Object.fromEntries(
  CAPABILITIES.map((item) => [item.key, item]),
) as Record<CapabilityName, (typeof CAPABILITIES)[number]>

export const STATUS_LABELS: Record<CapabilityVerificationStatus, string> = {
  unsupported: '未声明',
  unverified: '未验证',
  verified: '已验证',
  failed: '验证失败',
}

export const BASIC_ROLE_KEYS = ['default.chat', 'default.vision', 'default.embedding'] as const
export const DOCUMENT_ROLE_KEY = 'materials.vision'
export const DOCUMENT_CAPABILITIES: CapabilityName[] = ['text_chat', 'structured_output', 'vision']

export const ADVANCED_ROLE_GROUPS = [
  { id: 'intake', name: '需求确认', prefixes: ['intake.'] },
  { id: 'materials', name: '资料理解与检索', prefixes: ['materials.', 'retrieval.'] },
  { id: 'outline', name: '课程目录与知识点', prefixes: ['outline.', 'points.'] },
  { id: 'content', name: '教学内容制作', prefixes: ['content.'] },
  { id: 'tutor', name: '互动讲师', prefixes: ['tutor.'] },
] as const

export function rolesInGroup(roles: RoleDefinition[], prefixes: readonly string[]) {
  return roles.filter(
    (role) =>
      !BASIC_ROLE_KEYS.includes(role.key as (typeof BASIC_ROLE_KEYS)[number]) &&
      role.key !== DOCUMENT_ROLE_KEY &&
      prefixes.some((prefix) => role.key.startsWith(prefix)),
  )
}

export function providerName(providers: Array<{ id: number | null; name: string }>, id: number) {
  return providers.find((provider) => provider.id === id)?.name || '未知连接'
}

export function modelCanHandle(model: ModelConfig, role: RoleDefinition) {
  if (!model.is_enabled) return false
  return role.required_capabilities.every((key) => {
    const state = model.capabilities[key]
    if (!state.supported || state.status === 'unsupported' || state.status === 'failed') return false
    return !(['vision', 'embeddings'] as CapabilityName[]).includes(key) || state.status === 'verified'
  })
}

export function modelMismatchReason(model: ModelConfig, role: RoleDefinition) {
  if (!model.is_enabled) return '模型已停用'
  for (const key of role.required_capabilities) {
    const state = model.capabilities[key]
    const name = CAPABILITY_BY_KEY[key].shortName
    if (!state.supported || state.status === 'unsupported') return `未声明${name}能力`
    if (state.status === 'failed') return `${name}检测未通过`
    if (['vision', 'embeddings'].includes(key) && state.status !== 'verified') return `${name}能力未验证`
  }
  return ''
}

export function resolutionSourceLabel(source: string, requestedRole: string) {
  if (source === 'legacy.environment') return '.env 兼容配置'
  if (source === 'legacy.active_provider') return '旧版当前连接'
  const separator = source.indexOf(':')
  if (separator < 0) return source
  const scope = source.slice(0, separator)
  const role = source.slice(separator + 1)
  const scopeName = scope === 'course' ? '本课程' : scope === 'global' ? '全局' : '上级范围'
  if (role === requestedRole) return `${scopeName}单独设置`
  if (role === 'default.chat') return `${scopeName}默认文字模型`
  if (role === 'default.vision') return `${scopeName}默认图片模型`
  if (role === 'default.embedding') return `${scopeName}默认向量模型`
  return `${scopeName}设置`
}
