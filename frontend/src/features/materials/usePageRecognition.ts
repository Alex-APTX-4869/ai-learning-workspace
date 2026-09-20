import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { HttpError, errorMessage } from '../../shared/api'
import { visionApi, type PageScope, type RecognitionJob, type RecognitionPage, type RecognitionPlan } from './visionApi'

export function usePageRecognition(scope:()=>PageScope) {
  const view=ref<RecognitionPage|null>(null),plan=ref<RecognitionPlan|null>(null),job=ref<RecognitionJob|null>(null)
  const loading=ref(false),busy=ref(false),error=ref(''),uncertain=ref(false)
  let generation=0,disposed=false,timer:ReturnType<typeof setTimeout>|undefined
  let pending:{id:string;plan:RecognitionPlan}|null=null
  const active=computed(()=>!!job.value && ['queued','running'].includes(job.value.status))
  const key=(s:PageScope)=>`learning-space.page-recognition:${s.batchId}:${s.fileId}:${s.processId}:${s.page}`
  function remove(s:PageScope){try{localStorage.removeItem(key(s))}catch{/* 已有持久任务仍可查询 */}}
  function schedule(){clearTimeout(timer);if(!disposed&&active.value)timer=setTimeout(poll,1500)}
  async function poll(){
    const id=job.value?.id,s={...scope()},token=generation
    if(!id)return
    try{const next=await visionApi.job(s,id);if(token===generation&&!disposed){job.value=next;error.value='';schedule()}}
    catch(cause){if(token===generation&&!disposed)error.value=errorMessage(cause)}
  }
  async function load(){
    const token=++generation,s={...scope()}
    clearTimeout(timer);view.value=null;job.value=null;plan.value=null;pending=null;uncertain.value=false
    loading.value=true;busy.value=false;error.value=''
    try{
      const next=await visionApi.view(s)
      if(token!==generation||disposed)return
      view.value=next;job.value=next.jobs[0]||null
      try{pending=JSON.parse(localStorage.getItem(key(s))||'null')}catch{pending=null}
      if(pending){
        plan.value=pending.plan
        try{
          const saved=await visionApi.job(s,pending.id)
          if(token!==generation||disposed)return
          job.value=saved;remove(s);pending=null;plan.value=null
        }catch(cause){
          if(token!==generation||disposed)return
          uncertain.value=true
          error.value=cause instanceof HttpError&&cause.status===404 ? '上次提交尚未查到任务，可恢复同一请求；不会自动另发一次。' : errorMessage(cause)
        }
      }
      schedule()
    }catch(cause){if(token===generation&&!disposed)error.value=errorMessage(cause)}
    finally{if(token===generation&&!disposed)loading.value=false}
  }
  async function prepare(){
    if(busy.value||loading.value||uncertain.value)return
    const token=generation,s={...scope()};busy.value=true;error.value='';plan.value=null
    try{const next=await visionApi.plan(s);if(token===generation&&!disposed)plan.value=next}
    catch(cause){if(token===generation&&!disposed)error.value=errorMessage(cause)}
    finally{if(token===generation&&!disposed)busy.value=false}
  }
  async function start(){
    if(!plan.value||busy.value||loading.value)return
    const token=generation,s={...scope()}
    const request=pending||{id:crypto.randomUUID(),plan:plan.value}
    // 在网络请求前记录身份；刷新后先查询这一身份，不猜测请求是否成功。
    try{localStorage.setItem(key(s),JSON.stringify(request))}
    catch{error.value='浏览器无法保存请求身份，请启用本地存储后再试；本次未发送。';return}
    pending=request;busy.value=true;error.value=''
    try{
      const next=await visionApi.start(s,request.id,request.plan.plan_hash)
      remove(s)
      if(token===generation&&!disposed){job.value=next;pending=null;uncertain.value=false;plan.value=null;schedule()}
    }catch(cause){
      if(token!==generation||disposed)return
      error.value=errorMessage(cause)
      if(cause instanceof HttpError && [404,409,422].includes(cause.status)){remove(s);pending=null;plan.value=null;uncertain.value=false}
      else uncertain.value=true
    }finally{if(token===generation&&!disposed)busy.value=false}
  }
  async function review(decision:'accepted'|'rejected',note:string){
    if(!job.value||busy.value)return
    const token=generation,s={...scope()},current=job.value;busy.value=true;error.value=''
    try{const next=await visionApi.review(s,current,decision,note);if(token===generation&&!disposed)job.value=next}
    catch(cause){if(token===generation&&!disposed)error.value=errorMessage(cause)}
    finally{if(token===generation&&!disposed)busy.value=false}
  }
  watch(()=>JSON.stringify(scope()),load,{immediate:true})
  onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer)})
  return {view,plan,job,loading,busy,error,uncertain,active,load,poll,prepare,start,review}
}
