import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createRenderer,createSSRApp,nextTick,ref} from 'vue'
import {renderToString} from 'vue/server-renderer'
const vite=await createServer({server:{middlewareMode:true,watch:null},appType:'custom'})
let checks=0
const apps=[]
const check=async(name,fn)=>{await fn();checks++;console.log(`PASS ${name}`)}
const settle=async()=>{await nextTick();await new Promise(resolve=>setImmediate(resolve))}
const hit={file_id:'file',batch_id:'batch',process_id:'process',element_id:'e1',filename:'资料.pdf',locator:{type:'pdf_page',page:1},offset:0,excerpt:'文本',text_only:true}
const passage={...hit,text:'第一段',total_characters:6,next_offset:3,preview:null}
const result={method:'keyword',hits:[hit],total:1,scope_available:true,outline_version_id:2}
try {
  const {fileStatusText}=await vite.ssrLoadModule('/src/features/materials/labels.ts')
  await check('A saved text-only confirmation is not displayed as still awaiting approval',async()=>{
    const file={status:'needs_review',included:true,text_only_accepted:true}
    assert.equal(fileStatusText(file),'已确认，仅采用文字')
    assert.equal(fileStatusText({...file,text_only_accepted:false}),'需核对识别范围')
    assert.equal(fileStatusText({...file,status:'failed'}),'未完成')
    assert.equal(fileStatusText({...file,included:false}),'未纳入本次范围')
  })
  const {materialsApi}=await vite.ssrLoadModule('/src/features/materials/api.ts')
  const {useMaterialSearch}=await vite.ssrLoadModule('/src/features/materials/useMaterialSearch.ts')
  const renderer=createRenderer({createElement:()=>({}),createText:text=>({text}),createComment:text=>({text}),insert(){},remove(){},setText(){},setElementText(){},patchProp(){},parentNode:()=>null,nextSibling:()=>null})
  function mount() {
    let state
    const course=ref(1),outline=ref(2)
    const app=renderer.createApp({setup(){state=useMaterialSearch(course,outline);return()=>null}})
    app.mount({});apps.push(app)
    return {state,course,outline,app}
  }
  await check('Late search results cannot cross outline versions',async()=>{
    let resolve,signal
    materialsApi.search=async(_course,_outline,_query,_file,_page,s)=>{signal=s;return new Promise(r=>resolve=r)}
    const {state,outline}=mount()
    const pending=state.search('连接池','',null)
    outline.value=3;await settle()
    assert.equal(signal.aborted,true)
    resolve(result);await pending
    assert.equal(state.result.value,null)
    assert.equal(state.searching.value,false)
  })
  await check('The most recent search wins out-of-order responses',async()=>{
    const pending=[]
    materialsApi.search=()=>new Promise(resolve=>pending.push(resolve))
    const {state}=mount()
    const first=state.search('old','',null),second=state.search('new','',null)
    pending[1]({...result,total:2});await second
    pending[0]({...result,total:1});await first
    assert.equal(state.result.value.total,2)
  })
  await check('Closing a source ignores late reads without changing data',async()=>{
    let resolve,signal
    materialsApi.source=async(_course,_outline,_hit,_offset,s)=>{signal=s;return new Promise(r=>resolve=r)}
    const {state}=mount()
    const pending=state.read(hit)
    state.closeSource();resolve(passage);await pending
    assert.equal(signal.aborted,true)
    assert.equal(state.source.value,null)
    assert.equal(state.selected.value,null)
  })
  await check('Continuation appends only consecutive text from the selected source',async()=>{
    materialsApi.source=async(_course,_outline,_hit,offset)=>offset ? {...passage,offset:3,text:'第二段',next_offset:null} : passage
    const {state}=mount()
    await state.read(hit,0)
    await state.read(state.selected.value,3,true)
    assert.equal(state.source.value.text,'第一段第二段')
    assert.equal(state.source.value.offset,0)
    assert.equal(state.source.value.next_offset,null)
    await state.read({...hit,element_id:'e2'},0)
    assert.equal(state.source.value.text,'第一段')
  })
  await check('Failure is visible and a retry clears it',async()=>{
    const {state}=mount()
    materialsApi.search=async()=>{throw new Error('读取失败')}
    await state.search('422','',null)
    assert.equal(state.searchError.value,'读取失败')
    materialsApi.search=async()=>result
    await state.search('422','',null)
    assert.equal(state.searchError.value,'')
    assert.equal(state.result.value.hits.length,1)
  })
  await check('Source text is escaped, includes location, and is never rendered as HTML',async()=>{
    const Component=(await vite.ssrLoadModule('/src/features/materials/components/SourcePassageDialog.vue')).default
    const context={}
    await renderToString(createSSRApp(Component,{hit,source:{...passage,text:'<script>alert(1)</script>'},loading:false,error:''}),context)
    const html=context.teleports.body
    assert.match(html,/&lt;script&gt;/)
    assert.doesNotMatch(html,/<script>/)
    assert.match(html,/原文件第 1 页/)
    assert.match(html,/不是 AI 回答/)
  })
  await check('Content citations show only cited sources, with supplements explicitly labelled',async()=>{
    const Component=(await vite.ssrLoadModule('/src/features/learning/components/ContentSources.vue')).default
    const html=await renderToString(createSSRApp(Component,{courseId:1,outlineVersionId:2,
      evidence:{method:'keyword',sources:[{...hit,id:'S1'},{...hit,id:'S2',filename:'不应显示.pdf'}]},
      items:[{title:'讲解',source_kind:'source_based',source_ids:['S1']},{title:'类比',source_kind:'supplemental',source_ids:[]}]}))
    assert.match(html,/资料.pdf/);assert.match(html,/原文件第 1 页/)
    assert.match(html,/AI 补充内容，不是资料原文/);assert.doesNotMatch(html,/不应显示.pdf/)
    const legacy=await renderToString(createSSRApp(Component,{courseId:1,outlineVersionId:2,items:[]}))
    assert.doesNotMatch(legacy,/依据资料/)
  })
  console.log(`${checks} materials frontend checks passed`)
} finally {for(const app of apps) app.unmount();await vite.close()}
