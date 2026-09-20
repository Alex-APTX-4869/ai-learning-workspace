import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createRenderer,nextTick,ref} from 'vue'
const vite=await createServer({server:{middlewareMode:true,watch:null},appType:'custom'})
const store=new Map(),apps=[]
globalThis.localStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)}
const renderer=createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert(){},remove(){},setText(){},setElementText(){},patchProp(){},parentNode:()=>null,nextSibling:()=>null})
const settle=async()=>{await nextTick();await new Promise(r=>setImmediate(r))}
const plan={plan_hash:'a'.repeat(64),page:1,provider_name:'test',model:'test',base_url:'https://test.invalid/v1',maximum_calls:1}
const job={id:'test-job',page:1,process_id:'process',status:'queued',result:null,review:'pending'}
const page={page:1,filename:'合成.pdf',text:'合成文字',preview:'page-1.png',jobs:[]}
let count=0
try{
  const {visionApi}=await vite.ssrLoadModule('/src/features/materials/visionApi.ts')
  const {usePageRecognition}=await vite.ssrLoadModule('/src/features/materials/usePageRecognition.ts')
  const {HttpError}=await vite.ssrLoadModule('/src/shared/api.ts')
  const defaults=()=>{
    visionApi.view=async()=>page;visionApi.plan=async()=>plan;visionApi.start=async()=>job;visionApi.job=async()=>job
    visionApi.review=async(_s,j,decision,note)=>({...j,review:decision,review_note:note})
  }
  async function mount(){
    let state;const current=ref({batchId:'batch',fileId:'file',processId:'process',page:1})
    const app=renderer.createApp({setup(){state=usePageRecognition(()=>current.value);return()=>null}})
    app.mount({});apps.push(app);await settle();return{state,current,app}
  }
  async function check(name,fn){store.clear();defaults();await fn();for(const app of apps.splice(0))app.unmount();count++;console.log(`PASS ${name}`)}
  await check('Opening and planning never starts a paid request',async()=>{
    let calls=0;visionApi.start=async()=>{calls++;return job}
    const {state}=await mount();await state.prepare();assert.equal(calls,0);assert.equal(state.plan.value.maximum_calls,1)
  })
  await check('Explicit confirmation starts a persistent job and clears the plan',async()=>{
    const {state}=await mount();await state.prepare();await state.start()
    assert.equal(state.job.value.id,'test-job');assert.equal(state.active.value,true);assert.equal(state.plan.value,null)
  })
  await check('Uncertain network outcome retries the same request identity',async()=>{
    const ids=[];visionApi.start=async(_s,id)=>{ids.push(id);if(ids.length===1)throw new Error('network');return {...job,id}}
    const {state}=await mount();await state.prepare();await state.start();assert.equal(state.uncertain.value,true)
    await state.start();assert.equal(ids[0],ids[1]);assert.equal(state.uncertain.value,false)
  })
  await check('Reopening finds the persisted job without posting again',async()=>{
    let calls=0;visionApi.start=async()=>{calls++;throw new Error('unknown')}
    const first=await mount();await first.state.prepare();await first.state.start();first.app.unmount()
    const second=await mount();assert.equal(second.state.job.value.id,'test-job');assert.equal(calls,1);assert.equal(store.size,0)
  })
  await check('Late page results cannot replace a newly selected page',async()=>{
    let release;visionApi.view=async s=>s.page===1?new Promise(r=>release=r):({...page,page:2,text:'second'})
    const {state,current}=await mount();current.value={...current.value,page:2};await settle()
    release(page);await settle();assert.equal(state.view.value.page,2);assert.equal(state.view.value.text,'second')
  })
  await check('Closing stops local state changes but never cancels a server job',async()=>{
    let release;visionApi.start=async()=>new Promise(r=>release=r)
    const {state,app}=await mount();await state.prepare();const request=state.start();app.unmount();release(job);await request
    assert.equal(state.job.value,null);assert.equal(store.size,0)
  })
  await check('Changed page or model requires a fresh confirmation plan',async()=>{
    visionApi.start=async()=>{throw new HttpError('changed',409)}
    const {state}=await mount();await state.prepare();await state.start()
    assert.equal(state.plan.value,null);assert.equal(state.uncertain.value,false);assert.equal(store.size,0)
  })
  await check('Review records the user decision separately from recognized content',async()=>{
    visionApi.view=async()=>({...page,jobs:[{...job,status:'ready',result:{blocks:[],issues:['blank']}}]})
    const {state}=await mount();await state.review('rejected','公式不清楚')
    assert.equal(state.job.value.review,'rejected');assert.deepEqual(state.job.value.result,{blocks:[],issues:['blank']})
  })
  console.log(`${count} page recognition frontend checks passed`)
}finally{for(const app of apps)app.unmount();delete globalThis.localStorage;await vite.close()}
