<script setup lang="ts">
import { computed } from 'vue'
import type { LlmProvider, ModelConfig, RoleBinding, RoleDefinition, RoleResolutionState, SettingsScope } from '../types'
import RoleAssignmentRow from './RoleAssignmentRow.vue'

const props = defineProps<{
  role: RoleDefinition; scope: SettingsScope; providers: LlmProvider[]; models: ModelConfig[]
  binding?: RoleBinding; resolution?: RoleResolutionState; mutation: string; loading: boolean
}>()
const emit = defineEmits<{
  change: [role: RoleDefinition, modelId: number | null]
  showConnections: []
}>()
// 保持原有路由 key 和已保存绑定，只改善用户可见名称。
const documentRole = computed(() => ({...props.role, name: '文档识别',
  description: '读取扫描文字、公式、表格与图示。可以使用独立 API，也可以复用已有连接中的视觉模型。'}))
</script>

<template>
  <section class="document-settings" aria-labelledby="document-settings-title">
    <header>
      <div>
        <h3 id="document-settings-title">文档识别</h3>
        <p>先读懂资料，再交给摘要、课程生成和讲师使用；不由向量模型代替。</p>
      </div>
      <span class="integration-status">已接入单页核对</span>
    </header>
    <RoleAssignmentRow prominent :role="documentRole" :scope="scope" :providers="providers" :models="models"
      :binding="binding" :resolution="resolution" :mutation="mutation" :loading="loading"
      @change="(role,id)=>emit('change',role,id)" />
    <div class="document-guide">
      <p><strong>{{ resolution?.value ? '模型配置已就绪' : '先配置并验证视觉模型' }}</strong>。配置后，到已上传 PDF 的“识别与核对单页 PDF”入口选择页面，核对发送范围后再调用。上传不会自动发送整份 PDF。</p>
      <ol>
        <li>在“连接与模型”中添加或选用 API，填写服务方提供的模型 ID。</li>
        <li>为模型声明“文字对话、结构化结果、图片理解”，再点击“检测文档识别能力”。</li>
        <li>检测通过后，在上方选择模型；修改会自动保存，不改变其他 Agent 的分配。</li>
      </ol>
      <p>当前支持带图片输入的 OpenAI 兼容接口；专用 OCR 服务的其他接口格式尚未适配。基础看图检测通过，不代表复杂公式、图表的识别准确率已达标。</p>
      <button type="button" class="text-button" :disabled="!!mutation" @click="emit('showConnections')">添加 API / 检测模型能力 →</button>
    </div>
  </section>
</template>

<style scoped>
.document-settings {margin-top:24px;}
header {display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:11px;}
h3 {margin:0;font-size:12px;}
header p,.document-guide {font-size:11px;line-height:1.8;color:var(--muted);}
header p {margin-top:5px;}
.integration-status {flex-shrink:0;font-size:10px;color:#98703f;}
.document-guide {padding:12px 3px 0;}
.document-guide strong {font-weight:500;color:var(--body);}
ol {padding-left:20px;margin:8px 0;}
.text-button {border:0;background:none;color:var(--accent);padding:9px 0 0;font-size:11px;cursor:pointer;}
@media(max-width:620px){header{flex-direction:column;gap:6px;}}
</style>
