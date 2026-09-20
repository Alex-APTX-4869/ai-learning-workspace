<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { HttpError, errorMessage } from '../../../shared/api'
import { materialsApi } from '../api'
import { visionApi, type RecognitionJob } from '../visionApi'
import type { AnalysisPlan, MaterialBatch, MaterialFile } from '../types'
import { annotationKey, type AnnotationDraft } from '../useAnnotationAutosave'
import MaterialFileCard from './MaterialFileCard.vue'
const props = defineProps<{name: string; intro: string; storageKey?: string; purpose?: 'chapter'}>()
const emit = defineEmits<{
  state: [value: {blocked: boolean; batchId: string | null; ideaLocked: boolean}]
  restoreIdea: [name: string, intro: string]
}>()
const KEY=props.storageKey || 'learning-space.material-draft'
const IDEA=props.storageKey ? `${props.storageKey}:idea` : 'learning-space.material-idea'
const batch=ref<MaterialBatch|null>(null)
const plan=ref<AnalysisPlan|null>(null)
const loading=ref(true)
const restoreFailed=ref(false)
const mutation=ref('')
const pendingWrites=ref(0)
let writes: Promise<unknown> = Promise.resolve()
const error=ref('')
const dirty=ref<Record<string,boolean>>({})
const fileInput=ref<HTMLInputElement|null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let alive=true
let version=0
const editing=computed(()=>!batch.value || batch.value.status==='editing')
const included=computed(()=>batch.value?.files.filter(f=>f.included) || [])
const dirtyAny=computed(()=>Object.values(dirty.value).some(Boolean))
const analyzing=computed(()=>!!batch.value && ['queued','analyzing'].includes(batch.value.status))
const hasJobs=computed(()=>analyzing.value || batch.value?.files.some(f=>['queued','processing'].includes(f.status)))
watch([batch,loading,restoreFailed,pendingWrites,dirtyAny],()=>emit('state',{
  blocked:loading.value || restoreFailed.value || pendingWrites.value>0 || dirtyAny.value || (included.value.length>0 && !['ready','linked'].includes(batch.value?.status || '')),
  batchId:included.value.length ? batch.value?.id || null : null,
  ideaLocked:!!batch.value && !editing.value,
}),{immediate:true,deep:true})
watch(()=>[props.name,props.intro],()=>{
  if (batch.value && editing.value) localStorage.setItem(IDEA,JSON.stringify({id:batch.value.id,name:props.name,intro:props.intro}))
  plan.value=null
})
function schedule() {
  clearTimeout(timer)
  if (alive && hasJobs.value) timer=setTimeout(refresh,1500)
}
function apply(next:MaterialBatch) {batch.value=next; schedule()}
async function refresh() {
  if (!batch.value || !alive) return
  if (pendingWrites.value) {schedule();return}
  const current=version
  try {const next=await materialsApi.get(batch.value.id); if(alive && version===current) apply(next)}
  catch(cause) {if(alive) error.value=errorMessage(cause); schedule()}
}
async function run(action:()=>Promise<void>,label:string) {
  // 文件 A 的保存不能吞掉文件 B 的自动保存；所有草稿修改按顺序提交。
  pendingWrites.value++
  version++
  const result=writes.then(async()=>{
    mutation.value=label;error.value=''
    try {await action();return true} catch(cause) {error.value=errorMessage(cause);return false}
    finally {mutation.value='';pendingWrites.value--;schedule()}
  })
  writes=result
  return result
}
async function restore() {
  loading.value=true; restoreFailed.value=false; error.value=''
  const id=localStorage.getItem(KEY)
  try {
    if(id) {
      const saved=await materialsApi.get(id)
      if(saved.intake_id) {localStorage.removeItem(KEY);localStorage.removeItem(IDEA);return}
      apply(saved)
      let name=saved.name,intro=saved.intro
      try {const draft=JSON.parse(localStorage.getItem(IDEA)||'null');if(draft?.id===id && saved.status==='editing'){name=draft.name;intro=draft.intro}} catch { /* 使用服务端草稿 */ }
      emit('restoreIdea',name,intro)
    }
  } catch(cause) {
    if(cause instanceof HttpError && cause.status===404)localStorage.removeItem(KEY)
    else {error.value=errorMessage(cause);restoreFailed.value=true}
  } finally {loading.value=false;schedule()}
}
async function upload(event:Event) {
  const input=event.target as HTMLInputElement
  const files=Array.from(input.files||[])
  input.value=''
  await run(async()=>{
    if(!batch.value) {
      const id=crypto.randomUUID()
      apply(await materialsApi.create(id,props.name,props.intro))
      localStorage.setItem(KEY,id)
    }
    for(const file of files) {
      if(file.size>25*1024*1024)throw new Error(`《${file.name}》超过 25 MB，请拆分后上传。`)
      mutation.value=`正在上传 ${file.name}`
      // 同一文件断网后重选或刷新再上传，复用请求身份，避免多存一份。
      const bytes=await crypto.subtle.digest('SHA-256',await file.arrayBuffer())
      const hash=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('')
      const key=`learning-space.material-upload:${batch.value!.id}:${encodeURIComponent(file.name)}:${hash}`
      const requestId=localStorage.getItem(key)||crypto.randomUUID()
      localStorage.setItem(key,requestId)
      apply(await materialsApi.upload(batch.value!,file,requestId))
    }
    plan.value=null
  },'正在上传资料')
}
async function saveIdea() {
  if(batch.value && editing.value) apply(await materialsApi.save(batch.value.id,batch.value.revision,props.name,props.intro,batch.value.completeness))
}
async function saveFile(file:MaterialFile,draft:AnnotationDraft) {
  let failure:unknown
  const saved=await run(async()=>{
    try {
      const current=batch.value?.files.find(item=>item.id===file.id)
      if(!current || !editing.value)throw new Error('资料范围已固定，不能修改标注。')
      if(annotationKey(current)!==annotationKey(file))throw new Error('已保存标注发生变化，请刷新核对后重试。')
      apply(await materialsApi.annotate(batch.value!.id,file.id,current.revision,draft.annotations,draft.included,draft.text_only_accepted))
      plan.value=null
    } catch(cause) {failure=cause;throw cause}
  },'正在自动保存标注')
  if(!saved)throw failure || new Error('自动保存未完成，请重试。')
}
async function retryFile(file:MaterialFile) {
  await run(async()=>{apply(await materialsApi.retry(batch.value!.id,file.id,batch.value!.revision));plan.value=null},'正在重新安排解析')
}
async function adoptPage(file:MaterialFile,job:RecognitionJob,selected:boolean) {
  let failure:unknown
  const saved=await run(async()=>{
    try {
      const current=batch.value?.files.find(f=>f.id===file.id)
      if(!current || !editing.value || dirtyAny.value)throw new Error('请先完成标注保存，且保持资料处于编辑状态。')
      apply(await visionApi.adopt({batchId:batch.value!.id,fileId:file.id,processId:job.process_id,page:job.page},job,current.revision,selected))
      plan.value=null
    }catch(cause){failure=cause;throw cause}
  },'正在更新采用页面')
  if(!saved)throw failure || new Error('采用未完成，请刷新重试。')
}
async function prepare() {
  if(dirtyAny.value)return
  await run(async()=>{await saveIdea();plan.value=await materialsApi.plan(batch.value!.id)},'正在核对资料范围')
}
async function analyze() {
  if(!plan.value || dirtyAny.value || pendingWrites.value)return
  await run(async()=>{apply(await materialsApi.analyze(batch.value!.id,plan.value!));plan.value=null},'正在启动资料分析')
}
async function reopen() {
  await run(async()=>{apply(await materialsApi.reopen(batch.value!.id,batch.value!.revision));plan.value=null},'正在返回编辑')
}
async function completeness(event:Event) {
  const value=(event.target as HTMLSelectElement).value
  await run(async()=>{apply(await materialsApi.save(batch.value!.id,batch.value!.revision,props.name,props.intro,value));plan.value=null},'正在保存覆盖范围')
}
onMounted(restore)
onBeforeUnmount(()=>{alive=false;clearTimeout(timer)})
</script>
<template>
  <section class="upload-panel" aria-label="课程参考资料">
    <header><div><h3>参考资料 <span>可选</span></h3><p>先上传教材或笔记，再让 AI 结合资料了解你的学习需求。</p></div>
      <button type="button" class="button secondary small" :disabled="loading || !!mutation || !editing" @click="fileInput?.click()">＋ 上传资料</button>
    </header>
    <input ref="fileInput" class="file-input" type="file" accept=".pdf,.docx,.doc,.png,.jpg,.jpeg" multiple @change="upload" />
    <p v-if="loading" role="status">正在恢复资料草稿…</p>
    <p v-else-if="!batch?.files.length" class="helper">PDF、Word、PNG/JPEG；单份 25 MB。扫描页和图片目前会保留原件并提示待识别。</p>
    <p v-if="mutation" class="helper" role="status">{{ mutation }}…</p>
    <div v-if="error" class="material-error" role="alert">{{ error }} <button type="button" class="text-button" :disabled="!!mutation" @click="batch ? refresh() : restore()">刷新状态</button></div>
    <template v-if="batch">
      <MaterialFileCard v-for="file in batch.files" :key="file.id" :batch-id="batch.id" :file="file" :disabled="(!!mutation && mutation!=='正在自动保存标注') || !editing" :read-only="!editing" :save="saveFile"
        :adopt="adoptPage" @retry="retryFile" @dirty="(id,value)=>{dirty[id]=value;if(value)plan=null}" />
      <p v-if="dirtyAny" class="helper">标注修改后自动保存；填写不完整或保存失败时，请查看对应文件的提示。保存完成后可继续核对范围。</p>
      <div v-if="included.length" class="batch-actions">
        <label>本批资料的范围<select :value="batch.completeness" :disabled="!!mutation || !editing" @change="completeness">
          <option value="partial">这是部分资料，后续还会补充</option><option value="complete">这就是本次课程的全部资料</option>
        </select></label>
        <p class="helper">“全部”是上传范围声明，识别遗漏仍会单独列出。指定章节与页段会随资料一同固定。</p>
        <template v-if="editing || batch.status==='failed' || batch.status==='needs_attention'">
          <p v-if="batch.error" class="material-error">{{ batch.error }}</p>
          <button type="button" class="button secondary" :disabled="!!mutation || dirtyAny || hasJobs || !name.trim() || !intro.trim()" @click="prepare">{{ batch.status==='editing' ? '核对范围，准备分析资料' : '检查后重试资料分析' }}</button>
        </template>
        <div v-if="plan" class="analysis-plan">
          <p>将把已采用范围内的文字与标注发送给 <strong>{{ plan.provider_name }}</strong>（{{ plan.model }}）。</p>
          <p>{{ plan.file_count }} 份资料，{{ plan.parts }} 个文字片段，预计最多 {{ plan.maximum_calls }} 次分析请求；费用由服务方计收。</p>
          <p v-if="plan.vision_page_count">其中 {{ plan.vision_page_count }} 页使用你已核对并采用的视觉转录；将发送转录后的文字、公式及图表描述。</p>
          <p v-if="purpose === 'chapter'">分析后，点击生成预览会将摘要、标注和当前课程需求交给大纲模型，仅规划新增章节。本次不会发送原始文件和图片。</p>
          <p v-else>之后点击需求确认时，资料摘要和标注会发送给：{{ plan.intake_providers.join('、') }}。本次不会发送原始文件和图片。</p>
          <button type="button" class="button primary" :disabled="!!mutation || dirtyAny || pendingWrites>0" @click="analyze">开始分析资料</button>
        </div>
        <div v-if="analyzing" class="analysis-status" role="status"><span class="spinner" />正在分段分析，已保存 {{ batch.analysis_completed_steps }} 个步骤。关闭后会继续。</div>
        <div v-if="batch.context && batch.status==='ready'" class="analysis-ready">
          <strong>{{ purpose === 'chapter' ? '资料分析完成，可以生成新章节预览' : '资料分析完成，可以开始需求确认' }}</strong>
          <details v-for="file in batch.context.files" :key="file.file_id"><summary>{{ file.filename }} · 查看分析</summary><p>{{ file.analysis.summary }}</p><ul><li v-for="topic in file.analysis.topics" :key="topic">{{ topic }}</li></ul></details>
        </div>
        <button v-if="['ready','failed','needs_attention'].includes(batch.status)" type="button" class="text-button" :disabled="!!mutation" @click="reopen">返回修改资料或课程想法</button>
      </div>
      <p v-if="batch.files.length" class="helper">文件和已保存标注保留在本机。{{ purpose === 'chapter' ? '生成新章节预览后，本批资料范围固定。' : '进入需求确认后，本批资料范围固定。' }}</p>
    </template>
  </section>
</template>
<style scoped>
.upload-panel {margin-top:28px; padding-top:24px; border-top:1px solid var(--line); }header {display:flex; align-items:flex-start; justify-content:space-between; gap:16px;}h3 {font-size:15px; margin:0 0 6px;}h3 span {font-size:11px; font-weight:400; color:var(--muted); margin-left:5px;}header p,.helper {font-size:12px; line-height:1.8; color:var(--muted);}.helper {margin-top:10px;}
.file-input {display:none;}.material-error {color:#965942; font-size:12px; line-height:1.8; margin-top:12px;}.batch-actions {padding-top:18px;}label {display:block; font-size:12px;}select {display:block; width:100%; margin-top:7px; padding:10px; border:1px solid var(--line); background:var(--soft); border-radius:8px;}.batch-actions>.button {margin-top:12px;}.text-button {background:none; border:0; color:var(--accent); padding:10px 0; font-size:12px; cursor:pointer;}
.analysis-plan,.analysis-ready {padding:16px; margin-top:16px; border:1px solid var(--line); border-radius:10px; font-size:12px; line-height:1.8;}.analysis-plan p {margin-bottom:10px;}.analysis-status {display:flex;align-items:center;gap:10px;margin-top:18px;font-size:12px;}.analysis-ready summary {cursor:pointer;padding-top:10px;}.analysis-ready p {white-space:pre-wrap;}.analysis-ready ul {padding-left:18px;}
@media(max-width:640px) {header {flex-wrap:wrap;}.analysis-status {align-items:flex-start;}}
</style>
