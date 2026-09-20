<script setup lang="ts">
import { ref } from 'vue'
import type { MaterialFile } from '../types'
import { useAnnotationAutosave } from '../useAnnotationAutosave'
import type { AnnotationDraft } from '../useAnnotationAutosave'
import { fileStatusText, issueLabel } from '../labels'
import MaterialReportView from './MaterialReportView.vue'
import PageRecognitionDialog from './PageRecognitionDialog.vue'
import type { RecognitionJob } from '../visionApi'
const props = defineProps<{batchId: string; file: MaterialFile; disabled: boolean; readOnly?: boolean; save?: (file: MaterialFile, draft: AnnotationDraft) => Promise<void>; adopt?: (file:MaterialFile,job:RecognitionJob,selected:boolean)=>Promise<void>}>()
const emit = defineEmits<{
  retry: [file: MaterialFile]
  dirty: [fileId: string, dirty: boolean]
}>()
const reportOpen = ref(false)
const recognitionOpen = ref(false)
const {annotations,included,textOnly,dirty,saving,failure,cacheWarning,problem,changed,flush,useSaved} = useAnnotationAutosave({
  file:()=>props.file, batchId:props.batchId, disabled:()=>props.disabled, readOnly:()=>!!props.readOnly,
  save:async(file,draft)=>{if(!props.save)throw new Error('标注保存不可用');await props.save(file,draft)},
  dirty:value=>emit('dirty',props.file.id,value),
})
function add() {
  annotations.value.push({role:'auto',chapter:'',note:'',page_start:null,page_end:null}); changed()
}
function pageValue(event: Event) { const raw=(event.target as HTMLInputElement).value; return raw ? Number(raw) : null }
</script>
<template>
  <article class="file-card" :class="{excluded: !included}">
    <header><div><strong>{{ file.filename }}</strong><small>{{ (file.byte_size/1024/1024).toFixed(2) }} MB<span v-if="file.page_count"> · {{ file.page_count }} 页</span></small></div>
      <span class="file-status" :class="file.status">{{ file.vision_pages?.length ? '已选视觉转录' : fileStatusText(file) }}</span>
    </header>
    <p v-if="file.error" class="file-error">{{ file.error }} <button v-if="!readOnly" type="button" :disabled="disabled" @click="emit('retry',file)">重新解析</button></p>
    <div v-if="!readOnly" class="file-controls">
      <label class="check"><input v-model="included" type="checkbox" :disabled="disabled" @change="changed" />本次采用这份资料</label>
      <template v-if="included">
        <div v-for="(a,i) in annotations" :key="i" class="annotation-row">
          <div class="annotation-fields">
            <label>资料用途<select v-model="a.role" :disabled="disabled" @change="changed"><option value="auto">交给 AI 判断</option><option value="overview">课程总述</option><option value="chapter">指定章节</option><option value="reference">补充参考</option></select></label>
            <label v-if="a.role==='chapter'">所属章节<input v-model="a.chapter" maxlength="120" placeholder="例如：第 5 章 数据库" :disabled="disabled" @input="changed" /></label>
          </div>
          <div v-if="file.suffix==='.pdf' && file.page_count" class="page-range">
            <span>页码范围（留空为全文）</span>
            <input type="number" :value="a.page_start" :min="1" :max="file.page_count" aria-label="开始页" :disabled="disabled" @input="a.page_start=pageValue($event); changed()" />
            <span>—</span><input type="number" :value="a.page_end" :min="1" :max="file.page_count" aria-label="结束页" :disabled="disabled" @input="a.page_end=pageValue($event); changed()" />
          </div>
          <label>补充说明<textarea v-model="a.note" rows="2" maxlength="2000" placeholder="例如：这一部分只作总述，不代表后面各章的正文已上传。" :disabled="disabled" @input="changed" /></label>
          <button v-if="annotations.length>1" type="button" class="text-button" :disabled="disabled" @click="annotations.splice(i,1); changed()">移除这条标注</button>
        </div>
        <button v-if="file.suffix==='.pdf' && file.page_count" type="button" class="text-button" :disabled="disabled || annotations.length>=30" @click="add">＋ 将其他页段标注给另一章节</button>
        <div v-if="file.issues.length" class="review-note">
          <ul><li v-for="issue in file.issues" :key="issue">{{ issueLabel[issue] || '部分内容需要核对原文' }}</li></ul>
          <label class="check"><input v-model="textOnly" type="checkbox" :disabled="disabled" @change="changed" />我已核对，其余未采用视觉转录的页面仅使用已提取文字；未识别内容暂不纳入</label>
        </div>
      </template>
      <div class="card-actions" aria-live="polite">
        <small v-if="saving" role="status">正在自动保存…</small>
        <small v-else-if="failure" class="file-error" role="alert">保存未完成：{{ failure }} <button type="button" class="text-button" :disabled="disabled || !!problem" @click="flush">重试</button> <button type="button" class="text-button" :disabled="disabled" @click="useSaved">放弃未保存修改，采用已保存标注</button></small>
        <small v-else-if="problem" class="file-error">{{ problem }}</small>
        <small v-else role="status">{{ dirty ? '等待自动保存…' : '标注已保存 · 修改后自动保存' }}</small>
        <small v-if="!included">排除后仍保留原文件</small>
      </div>
      <small v-if="cacheWarning" class="file-error" role="alert">{{ cacheWarning }}</small>
    </div>
    <p v-else class="annotations-read">{{ file.annotations.map(a => `${({overview:'总述',chapter:'指定章节',reference:'补充参考',auto:'交给 AI 判断'})[a.role]}${a.chapter?' · '+a.chapter:''}${a.page_start?' · 第 '+a.page_start+'–'+a.page_end+' 页':''}${a.note?'：'+a.note:''}`).join('；') }}</p>
    <button v-if="file.status==='ready' || file.status==='needs_review'" type="button" class="text-button report-toggle" @click="reportOpen=!reportOpen">{{ reportOpen ? '收起解析报告' : readOnly ? '查看完整解析报告（含未纳入页）' : '查看提取文字与原页' }}</button>
    <MaterialReportView v-if="reportOpen" :batch-id="batchId" :file="file" />
    <button v-if="file.suffix==='.pdf' && file.process_id && file.page_count && ['ready','needs_review'].includes(file.status)" type="button" class="text-button" @click="recognitionOpen=true">识别与核对单页 PDF</button>
    <p v-if="file.vision_pages?.length" class="annotations-read">已选视觉转录：第 {{ file.vision_pages.map(p=>p.page).join('、') }} 页。分析时只纳入标注范围内的页面。</p>
    <PageRecognitionDialog v-if="recognitionOpen" :batch-id="batchId" :file="file" :adoption-disabled="disabled || dirty || saving" :adopt="adopt ? (job,selected)=>adopt!(file,job,selected) : undefined" @close="recognitionOpen=false" />
  </article>
</template>
<style scoped>
.file-card { border: 1px solid var(--line); border-radius: 12px; padding: 18px; background: var(--surface); margin-top: 12px; }
header { display:flex; justify-content: space-between; gap: 12px; } header > div { min-width:0; } strong { font-size: 13px; overflow-wrap:anywhere; } small { display:block; color:var(--muted); font-size:11px; margin-top:5px; }
.file-status { white-space:nowrap; color:var(--muted); font-size:11px; }.needs_review,.failed,.file-error { color:#91623e; }.file-error {font-size:12px; line-height:1.7; margin-top:12px; }
.file-controls { margin-top:15px; }.check { display:flex; align-items:flex-start; gap:8px; line-height:1.7; }.check input {width:14px; height:14px; margin-top:4px; flex-shrink:0;}
label { display:block; margin:10px 0 5px; font-size:12px; font-weight:normal; }select,input,textarea { display:block; width:100%; margin-top:5px; padding:8px 10px; font-size:12px; border:1px solid var(--line); border-radius:7px; background:var(--soft); color:var(--ink); }
.annotation-fields { display:grid; grid-template-columns:1fr 1fr; gap:12px; }.annotation-row { margin-top:12px; padding-top:4px; border-top:1px solid var(--line); }
.page-range {display:flex; align-items:center; gap:6px; flex-wrap:wrap; font-size:11px; color:var(--muted); }.page-range input {width:65px; }
.text-button {border:0; background:none; padding:8px 0; color:var(--accent); font-size:12px; cursor:pointer; }.review-note {font-size:12px; line-height:1.7; color:#785b3a; margin-top:10px; }.review-note ul {padding-left:18px;}
.card-actions {display:flex; align-items:center; gap:12px; margin-top:14px; }.annotations-read {white-space:pre-wrap; font-size:12px; color:var(--muted); margin-top:10px;}.excluded {background:var(--soft);}
@media(max-width:640px) {.annotation-fields {grid-template-columns:1fr;} header {flex-wrap:wrap;} .file-card {padding:14px;} }
</style>
