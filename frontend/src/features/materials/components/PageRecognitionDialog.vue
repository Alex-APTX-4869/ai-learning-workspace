<script setup lang="ts">
import { ref, watch } from 'vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import SafeMarkdown from '../../learning/components/SafeMarkdown.vue'
import { materialsApi } from '../api'
import { usePageRecognition } from '../usePageRecognition'
import type { MaterialFile } from '../types'
import { visionApi, type RecognitionJob } from '../visionApi'
import { errorMessage } from '../../../shared/api'
const props=defineProps<{batchId:string;file:MaterialFile;adoptionDisabled?:boolean;adopt?:(job:RecognitionJob,selected:boolean)=>Promise<void>}>()
const emit=defineEmits<{close:[]}>()
const page=ref(1),note=ref('')
const adopting=ref(false),adoptionError=ref('')
const {view,plan,job,loading,busy,error,uncertain,active,load,poll,prepare,start,review}=usePageRecognition(()=>({
  batchId:props.batchId,fileId:props.file.id,processId:props.file.process_id!,page:page.value,
}))
watch(()=>job.value?.id,()=>{note.value=job.value?.review_note||''})
const kinds={text:'文字',formula:'公式 · LaTeX 源码',table:'表格',diagram:'图示说明'}
async function choosePage(selected:boolean) {
  if(!job.value || !props.adopt || adopting.value)return
  adopting.value=true;adoptionError.value=''
  try {
    const target=!selected && view.value?.adoption && view.value.adoption.recognition_id!==job.value.id
      ? await visionApi.job({batchId:props.batchId,fileId:props.file.id,processId:props.file.process_id!,page:page.value},view.value.adoption.recognition_id)
      : job.value
    await props.adopt(target,selected);await load()
  }
  catch(cause){adoptionError.value=errorMessage(cause)}
  finally{adopting.value=false}
}
</script>
<template>
  <BaseDialog open wide labelledby="recognition-title" @close="emit('close')">
    <div class="recognition-dialog">
      <header><div><h2 id="recognition-title">单页识别与核对</h2><p>{{ file.filename }}</p></div><button type="button" aria-label="关闭单页识别" @click="emit('close')">关闭</button></header>
      <div class="recognition-scroll">
        <div class="page-toolbar">
          <label>PDF 物理页码 <select v-model.number="page" :disabled="busy || loading"><option v-for="n in file.page_count || 1" :key="n" :value="n">第 {{ n }} 页</option></select></label>
          <button type="button" :disabled="busy || loading || active || uncertain || !view" @click="prepare">核对发送范围{{ job?.status==='failed'||job?.status==='interrupted'||job?.review==='rejected' ? '，重试本页' : '' }}</button>
        </div>
        <p class="notice">仅识别你选择的这一页。核对通过后，可在资料草稿中明确采用；分析开始后固定修订，不自动改变已有课程。</p>
        <p v-if="view?.adoption" class="notice">本页已选转录修订：{{ view.adoption.recognition_id.slice(0,8) }}。{{ !view.editable ? '资料范围已固定，新的识别结果不会替换旧课程依据。' : '开始分析前仍可取消或更换。' }}</p>
        <p v-if="adoptionError" class="error" role="alert">{{ adoptionError }}</p>
        <p v-if="loading" role="status">正在读取原页和已保存结果…</p>
        <p v-if="error" class="error" role="alert">{{ error }} <button type="button" :disabled="busy" @click="uncertain ? start() : active ? poll() : load()">{{ uncertain ? '恢复上次提交' : '刷新状态' }}</button></p>
        <div v-if="plan" class="send-plan">
          <strong>{{ plan.maximum_calls ? '将发送' : '将复用' }}第 {{ plan.page }} 页{{ plan.maximum_calls ? '，接收方：' : '已有任务：' }}{{ plan.provider_name }} · {{ plan.model }}</strong>
          <p>{{ plan.base_url }}</p><p>1 张页面图片（{{ Math.ceil(plan.image_bytes/1024) }} KB）＋同页 {{ plan.text_characters }} 字辅助文字；不会上传整份 PDF。</p>
          <p>{{ plan.maximum_calls ? '最多 1 次模型请求，可能产生费用。失败不会自动再次调用。' : '已有相同输入和模型的任务，将复用，不新增模型请求。' }}</p>
          <button type="button" :disabled="busy" @click="start">{{ busy ? '正在提交…' : uncertain ? '恢复同一请求' : plan.maximum_calls ? '确认发送并识别本页' : '查看已有任务' }}</button>
        </div>
        <div v-if="view" class="comparison">
          <section><h3>原文件第 {{ page }} 页</h3><a :href="materialsApi.artifact(batchId,file.id,file.process_id!,view.preview)" target="_blank" rel="noopener noreferrer">打开大图核对</a>
            <img :src="materialsApi.artifact(batchId,file.id,file.process_id!,view.preview)" :alt="`原文件第 ${page} 页`" />
            <details><summary>查看本机提取文字（可能错位）</summary><p class="raw">{{ view.text || '未提取到文字，将依靠图片识别。' }}</p></details>
          </section>
          <section><h3>识别结果</h3>
            <p v-if="!job" class="notice">尚未识别。先核对上方的发送范围，再确认调用。</p>
            <template v-else>
              <p class="notice">{{ job.provider_name }} · {{ job.model }}</p>
              <p v-if="active" role="status">{{ job.status==='queued' ? '等待后台处理…' : '正在识别这一页…' }}关闭窗口不会中断，可稍后回来查看。</p>
              <p v-if="job.error" class="error">{{ job.error }}</p>
              <button v-if="!job.result && adopt && view?.editable && view.adoption" type="button" :disabled="busy || adopting || adoptionDisabled" @click="choosePage(false)">取消采用此页的旧修订</button>
              <template v-if="job.result">
                <p class="notice">{{ ({pending:'AI 转录 · 待人工核对',accepted:'已由你标记核对通过',rejected:'已标记识别有误'})[job.review] }}。核对通过仅记录你的判断，不代表整份文件识别完成。</p>
                <ul v-if="job.result.issues.length" class="error"><li v-for="(issue,i) in job.result.issues" :key="i">{{ issue }}</li></ul>
                <article v-for="(block,i) in job.result.blocks" :key="i">
                  <small>{{ kinds[block.kind] }}{{ block.uncertain ? ' · 存疑' : '' }}</small><h4>{{ block.title }}</h4>
                  <pre v-if="block.kind==='formula'">{{ block.content }}</pre><SafeMarkdown v-else :source="block.content" />
                  <p v-if="block.note" class="error">{{ block.note }}</p>
                </article>
                <label class="review-note">核对备注（可选）<textarea v-model="note" maxlength="1000" rows="2" :disabled="busy" placeholder="例如：第二个公式下标识别有误" /></label>
                <div class="review-actions"><button type="button" :disabled="busy || adopting" @click="review('accepted',note)">核对通过</button><button type="button" :disabled="busy || adopting" @click="review('rejected',note)">识别有误</button></div>
                <div v-if="adopt && view?.editable" class="review-actions">
                  <button type="button" :disabled="busy || adopting || adoptionDisabled || job.review!=='accepted'" @click="choosePage(true)">{{ adopting ? '正在更新…' : '本次课程采用此页' }}</button>
                  <button v-if="view.adoption" type="button" :disabled="busy || adopting || adoptionDisabled" @click="choosePage(false)">取消采用此页</button>
                </div>
              </template>
            </template>
          </section>
        </div>
      </div>
    </div>
  </BaseDialog>
</template>
<style scoped>
.recognition-dialog{height:100%;display:flex;flex-direction:column;background:var(--surface);}
header{display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid var(--line);gap:16px;flex-shrink:0;}
h2{font-size:18px;}header p{font-size:12px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere;}
.recognition-scroll{min-height:0;overflow-y:auto;padding:20px 24px;}
.page-toolbar,.review-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;}
button,select{border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--ink);background:var(--soft);font-size:12px;cursor:pointer;}
button:disabled{opacity:.5;cursor:default;}label{font-size:12px;}
.notice,.send-plan p{font-size:12px;line-height:1.8;color:var(--muted);margin:10px 0;}
.send-plan{padding:16px;border:1px solid var(--line);border-radius:10px;margin:14px 0;font-size:13px;overflow-wrap:anywhere;}
.comparison{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start;margin-top:20px;}
section{min-width:0;}h3{font-size:15px;margin-bottom:12px;}img{width:100%;height:auto;display:block;margin-top:8px;border:1px solid var(--line);}
a,summary{font-size:12px;color:var(--accent);cursor:pointer;}article{border-top:1px solid var(--line);padding:16px 0;}h4{font-size:14px;margin:6px 0 12px;}small{font-size:11px;color:var(--muted);}
pre,.raw{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font-size:13px;line-height:1.8;}
.error{font-size:12px;line-height:1.8;color:#965942;overflow-wrap:anywhere;}ul{padding-left:18px;}
.review-note{display:block;margin:16px 0 8px;}textarea{display:block;width:100%;margin-top:6px;padding:8px;border:1px solid var(--line);border-radius:8px;}
@media(max-width:700px){.comparison{grid-template-columns:1fr;}.recognition-scroll{padding:16px;}header{padding:16px;}}
</style>
