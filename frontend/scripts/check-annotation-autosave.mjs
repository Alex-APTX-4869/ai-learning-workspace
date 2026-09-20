import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createRenderer, createSSRApp, nextTick, ref, ssrContextKey} from 'vue'
import {renderToString} from 'vue/server-renderer'

const vite=await createServer({server:{middlewareMode:true,watch:null},appType:'custom'})
const storage=new Map(), apps=[]
globalThis.localStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}
const renderer=createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert(){},remove(){},setText(){},setElementText(){},patchProp(){},parentNode:()=>null,nextSibling:()=>null})
const settle=async()=>{await nextTick();await new Promise(r=>setImmediate(r))}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
let checks=0
const check=async(name,fn)=>{storage.clear();await fn();for(const app of apps.splice(0))app.unmount();checks++;console.log(`PASS ${name}`)}
const file=(id='one')=>({id,filename:'合成测试.pdf',suffix:'.pdf',byte_size:100,revision:1,included:true,text_only_accepted:false,
  annotations:[{role:'auto',chapter:'',note:'',page_start:null,page_end:null}],status:'ready',page_count:10,issues:[],error:null})
try {
  const {useAnnotationAutosave}=await vite.ssrLoadModule('/src/features/materials/useAnnotationAutosave.ts')
  function mount({source=file(),save,disabled=false,delay=10000,readOnly=false}={}) {
    const current=ref(source),busy=ref(disabled),calls=[],dirtyEvents=[]
    let state
    const app=renderer.createApp({setup(){
      state=useAnnotationAutosave({file:()=>current.value,batchId:'test',disabled:()=>busy.value,readOnly:()=>readOnly,delay,
        dirty:value=>dirtyEvents.push(value),save:async(base,draft)=>{
          calls.push(structuredClone(draft))
          if(save)await save(base,draft)
          current.value={...current.value,...structuredClone(draft),revision:current.value.revision+1}
          await nextTick()
        }})
      return()=>null
    }})
    app.mount({});apps.push(app)
    return {state,current,busy,calls,dirtyEvents,app}
  }
  await check('Typing is debounced and saves only the latest snapshot',async()=>{
    const m=mount({delay:15})
    m.state.annotations.value[0].note='a';m.state.changed()
    m.state.annotations.value[0].note='abc';m.state.changed()
    await wait(50)
    assert.equal(m.calls.length,1);assert.equal(m.calls[0].annotations[0].note,'abc')
    assert.equal(m.state.dirty.value,false);assert.equal(storage.size,0)
    assert.equal(m.calls[0].text_only_accepted,false)
  })
  await check('Incomplete chapter and page fields wait without issuing invalid requests',async()=>{
    const m=mount()
    const a=m.state.annotations.value[0]
    a.role='chapter';m.state.changed();await m.state.flush();assert.equal(m.calls.length,0)
    assert.match(m.state.problem.value,/所属章节/)
    a.chapter='第二章';a.page_start=2;m.state.changed();await m.state.flush();assert.equal(m.calls.length,0)
    a.page_end=12;m.state.changed();await m.state.flush();assert.equal(m.calls.length,0)
    a.page_end=4;m.state.changed();await m.state.flush();assert.equal(m.calls.length,1)
  })
  await check('Edits made during a request survive its acknowledgement',async()=>{
    let release
    const m=mount({save:()=>new Promise(r=>release=r)})
    m.state.annotations.value[0].note='first';m.state.changed()
    const pending=m.state.flush()
    m.state.annotations.value[0].note='second';m.state.changed()
    release();await pending
    assert.equal(m.state.annotations.value[0].note,'second');assert.equal(m.state.dirty.value,true)
    const second=m.state.flush();release();await second
    assert.deepEqual(m.calls.map(c=>c.annotations[0].note),['first','second'])
    assert.equal(m.state.dirty.value,false)
  })
  await check('Network failure retains the draft and can be explicitly retried',async()=>{
    let fail=true
    const m=mount({save:async()=>{if(fail)throw new Error('网络断开')}})
    m.state.annotations.value[0].note='保留';m.state.changed();await m.state.flush()
    assert.equal(m.state.failure.value,'网络断开');assert.equal(m.state.dirty.value,true);assert.equal(storage.size,1)
    fail=false;await m.state.flush()
    assert.equal(m.state.failure.value,'');assert.equal(m.state.dirty.value,false)
  })
  await check('Background revision updates cannot erase unsaved input',async()=>{
    const m=mount()
    m.state.annotations.value[0].note='draft';m.state.changed()
    m.current.value={...file(),revision:2};await settle()
    assert.equal(m.state.annotations.value[0].note,'draft')
    await m.state.flush();assert.equal(m.state.dirty.value,false)
  })
  await check('Conflicting saved annotations are never silently overwritten',async()=>{
    const m=mount()
    m.state.annotations.value[0].note='mine';m.state.changed()
    const other=file();other.annotations[0].note='another editor';other.revision=2
    m.current.value=other;await settle();await m.state.flush()
    assert.equal(m.calls.length,0);assert.match(m.state.failure.value,/未覆盖/)
    m.state.useSaved();assert.equal(m.state.annotations.value[0].note,'another editor');assert.equal(m.state.dirty.value,false)
  })
  await check('Closing and reopening restores a pending local draft',async()=>{
    const first=mount();first.state.annotations.value[0].note='restore me';first.state.changed();first.app.unmount()
    const second=mount()
    assert.equal(second.state.annotations.value[0].note,'restore me');assert.equal(second.state.dirty.value,true)
    await second.state.flush();assert.equal(second.state.dirty.value,false)
  })
  await check('A late response cannot delete a newer reopened draft',async()=>{
    let release
    const first=mount({save:()=>new Promise(r=>release=r)})
    first.state.annotations.value[0].note='old';first.state.changed();const pending=first.state.flush();first.app.unmount()
    const second=mount();second.state.annotations.value[0].note='new';second.state.changed()
    release();await pending
    const cached=JSON.parse([...storage.values()][0])
    assert.equal(cached.draft.annotations[0].note,'new')
  })
  await check('A draft resumes after an unrelated upload stops disabling the fields',async()=>{
    const m=mount({disabled:true,delay:15})
    m.state.annotations.value[0].note='queued';m.state.changed();await m.state.flush();assert.equal(m.calls.length,0)
    m.busy.value=false;await wait(50);assert.equal(m.calls.length,1)
  })
  await check('Read-only material views never restore or submit editing drafts',async()=>{
    const edit=mount();edit.state.annotations.value[0].note='private draft';edit.state.changed();edit.app.unmount()
    const m=mount({readOnly:true});await m.state.flush()
    assert.equal(m.state.annotations.value[0].note,'');assert.equal(m.calls.length,0)
  })
  await check('File card shows automatic-save status instead of a Save button',async()=>{
    const Card=(await vite.ssrLoadModule('/src/features/materials/components/MaterialFileCard.vue')).default
    const html=await renderToString(createSSRApp(Card,{batchId:'test',file:file(),disabled:false}))
    assert.match(html,/修改后自动保存/);assert.doesNotMatch(html,/>保存标注<|>标注已保存<\/button>/)
  })
  await check('Concurrent saves of different files are serialized by the upload panel',async()=>{
    const {materialsApi}=await vite.ssrLoadModule('/src/features/materials/api.ts')
    const Panel=(await vite.ssrLoadModule('/src/features/materials/components/MaterialsUploadPanel.vue')).default
    const batch={id:'test',name:'test',intro:'test',revision:1,status:'editing',files:[file('a'),file('b')],completeness:'partial',intake_id:null}
    storage.set('learning-space.material-draft','test')
    materialsApi.get=async()=>structuredClone(batch)
    const calls=[],releases=[]
    materialsApi.annotate=async(_batch,id,_revision,annotations,included,textOnly)=>{
      calls.push(id);await new Promise(r=>releases.push(r))
      const current=batch.files.find(f=>f.id===id)
      current.annotations=annotations;current.included=included;current.text_only_accepted=textOnly;current.revision++;batch.revision++
      return structuredClone(batch)
    }
    const app=renderer.createApp({...Panel,render(){return null}},{name:'test',intro:'test'})
    app.provide(ssrContextKey,{})
    app.mount({});apps.push(app);await settle()
    const state=app._instance.setupState
    const a=file('a'),b=file('b')
    const p1=state.saveFile(a,{...a,annotations:[{...a.annotations[0],note:'A'}]})
    const p2=state.saveFile(b,{...b,annotations:[{...b.annotations[0],note:'B'}]})
    await settle();assert.deepEqual(calls,['a'])
    releases[0]();await p1;await settle();assert.deepEqual(calls,['a','b'])
    releases[1]();await p2
    assert.deepEqual(state.batch.files.map(f=>f.annotations[0].note),['A','B'])
    assert.equal(state.pendingWrites,0)
  })
  console.log(`${checks} annotation autosave checks passed`)
} finally {for(const app of apps)app.unmount();await vite.close();delete globalThis.localStorage}
