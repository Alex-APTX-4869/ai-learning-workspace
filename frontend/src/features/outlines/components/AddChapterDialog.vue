<script setup lang="ts">
import { ref, onMounted } from 'vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import { request, errorMessage } from '../../../shared/api'
import MaterialsUploadPanel from '../../materials/components/MaterialsUploadPanel.vue'
import OutlinePreview from './OutlinePreview.vue'
import type { OutlineChapter } from '../types'
const props = defineProps<{courseId: number; versionId: number}>()
const emit = defineEmits<{close: []; published: []}>()
interface Draft {id: string; base_version_id: number; revision: number; status: string; additions_json: OutlineChapter[]; published_version_id: number|null}
const draft = ref<Draft|null>(null)
const name = ref(''), requirements = ref(''), busy = ref(false), error = ref('')
const materials = ref({blocked: true, batchId: null as string|null, ideaLocked: false})
const key = `learning-space.add-chapter:${props.courseId}:${props.versionId}`
const url = `/courses/${props.courseId}/directory-drafts`
onMounted(async () => {
  busy.value = true
  try {
    const stored = localStorage.getItem(key)
    if (stored) {
      draft.value = await request<Draft>(`${url}/${stored}`)
      if(draft.value.status === 'published') draft.value = null
    }
    if(!draft.value) draft.value = await request<Draft>(url, {method:'POST'})
    if(draft.value.base_version_id !== props.versionId) throw new Error('目录版本已变化，请关闭并重新打开。')
    localStorage.setItem(key, draft.value.id)
    const idea = JSON.parse(localStorage.getItem(`${key}:idea`) || '{}')
    name.value = idea.name || ''; requirements.value = idea.requirements || ''
  } catch(cause) {error.value = errorMessage(cause)}
  finally {busy.value = false}
})
async function generate() {
  if(!draft.value) return
  busy.value = true; error.value = ''
  localStorage.setItem(`${key}:idea`, JSON.stringify({name:name.value, requirements:requirements.value}))
  try {
    draft.value = await request<Draft>(`${url}/${draft.value.id}/generate-chapter`, {method:'POST', body:JSON.stringify({
      expected_revision:draft.value.revision, name:name.value.trim(), requirements:requirements.value.trim(), material_batch_id:materials.value.batchId,
    })})
  } catch(cause) {
    error.value = errorMessage(cause)
    try {draft.value = await request<Draft>(`${url}/${draft.value!.id}`)} catch { /* 下次打开恢复服务端草稿 */ }
  } finally {busy.value = false}
}
async function publish() {
  if(!draft.value) return
  busy.value = true; error.value = ''
  try {
    await request(`${url}/${draft.value.id}/publish`, {method:'POST',body:JSON.stringify({expected_revision:draft.value.revision})})
    localStorage.removeItem(key); localStorage.removeItem(`${key}:idea`)
    emit('published')
  } catch(cause) {error.value = errorMessage(cause)}
  finally {busy.value = false}
}
async function startNewDraft() {
  busy.value = true; error.value = ''
  try {
    const next = await request<Draft>(url, {method:'POST'})
    if(next.base_version_id !== props.versionId) throw new Error('目录已切换，请关闭并重新打开。')
    draft.value = next; localStorage.setItem(key, next.id)
    materials.value = {blocked:true,batchId:null,ideaLocked:false}
  } catch(cause) {error.value = errorMessage(cause)}
  finally {busy.value = false}
}
</script>
<template>
  <BaseDialog open wide labelledby="add-chapter-title" :busy="busy" @close="emit('close')">
    <div class="append-dialog">
      <header><div><h2 id="add-chapter-title">增加章节</h2><p>基于当前版本，只增加一章。确认后保存为新版本，保留原章节、知识点和资料。</p></div>
        <button class="button secondary small" :disabled="busy" @click="emit('close')">关闭</button></header>
      <p v-if="error" class="notice error-message" role="alert">{{ error }}</p>
      <template v-if="draft?.additions_json.length">
        <h3>新章节预览</h3><OutlinePreview :chapters="draft.additions_json" />
        <p>小节将全部放在这一个章节内。加入后可点击“生成知识点”，继续制作内容。</p>
        <button class="button primary" :disabled="busy" @click="publish">{{ busy ? '正在保存…' : '确认加入课程 · 保存新版本' }}</button>
        <button class="button secondary" :disabled="busy" @click="startNewDraft">不采用此预览，重新填写</button>
      </template>
      <form v-else-if="draft" @submit.prevent="generate">
        <fieldset :disabled="busy">
          <label>新增章节名称<input v-model="name" maxlength="200" required placeholder="例如：第 5 章 神经网络" :disabled="materials.ideaLocked" /></label>
          <label>这一章要学习什么？<textarea v-model="requirements" maxlength="12000" required rows="3" :disabled="materials.ideaLocked" /></label>
          <p>可选：上传新资料，在每份文件中标注章节、用途及页码；无资料也可以继续。上传后先完成资料分析。</p>
          <MaterialsUploadPanel :key="draft.id" purpose="chapter" :storage-key="`${key}:materials:${draft.id}`" :name="name" :intro="requirements"
            @state="materials = $event" @restore-idea="(n, i) => {name=n; requirements=i}" />
          <button class="button primary" :disabled="busy || materials.blocked || !name.trim() || !requirements.trim()">
            {{ busy ? '正在规划新章节…' : '生成新章节预览' }}
          </button>
        </fieldset>
      </form>
      <p v-if="busy" role="status">正在处理，请稍候。尚未确认的预览不会改变原目录。</p>
    </div>
  </BaseDialog>
</template>
<style scoped>
.append-dialog {padding:28px;overflow-y:auto;width:100%;}
header {display:flex;justify-content:space-between;gap:20px;margin-bottom:24px;}
p {font-size:13px;color:var(--muted);line-height:1.8;margin:12px 0;}
fieldset {border:0;padding:0;margin:0;min-width:0;}
label {display:flex;flex-direction:column;gap:8px;margin-bottom:18px;font-size:13px;}
.button.primary {margin-top:20px;}
</style>
