import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'
const vite=await createServer({server:{middlewareMode:true,watch:null},appType:'custom'})
let count=0
const check=async(name,fn)=>{await fn();count++;console.log(`PASS ${name}`)}
const role={key:'materials.vision',name:'文档识别',description:'资料图片',required_capabilities:['text_chat','structured_output','vision'],default_role:'default.vision'}
const model={id:1,provider_id:1,label:'视觉模型',model:'vision-test',is_enabled:true,revision:1,capabilities:Object.fromEntries(
  ['text_chat','structured_output','streaming','vision','embeddings'].map(key=>[key,{supported:key!=='embeddings',status:key==='embeddings'?'unsupported':'verified'}]))}
const providers=[{id:1,name:'测试连接'}],scope={type:'global',id:null}
try {
  const {modelCanHandle,modelMismatchReason,rolesInGroup,DOCUMENT_CAPABILITIES}=await vite.ssrLoadModule('/src/features/settings/modelCatalog.ts')
  const Card=(await vite.ssrLoadModule('/src/features/settings/components/ModelCard.vue')).default
  const Document=(await vite.ssrLoadModule('/src/features/settings/components/DocumentRecognitionSettings.vue')).default
  const Panel=(await vite.ssrLoadModule('/src/features/settings/components/RoleAssignmentsPanel.vue')).default
  await check('Document detection tests exactly chat, structured data, and images',()=>{
    assert.deepEqual(DOCUMENT_CAPABILITIES,['text_chat','structured_output','vision'])
  })
  await check('Unverified or failed image capability cannot be assigned',()=>{
    assert.equal(modelCanHandle(model,role),true)
    for(const status of ['unverified','failed','unsupported']){
      const candidate={...model,capabilities:{...model.capabilities,vision:{supported:true,status}}}
      assert.equal(modelCanHandle(candidate,role),false)
      assert.match(modelMismatchReason(candidate,role),/未验证|未通过|未声明/)
    }
  })
  await check('Document recognition appears outside advanced settings, exactly once',async()=>{
    const html=await renderToString(createSSRApp(Panel,{courses:[],scope,providers,models:[model],roles:[role],bindings:[],resolutions:{},loadingRoutes:false,mutation:''}))
    assert.ok(html.indexOf('id="document-settings-title"')<html.indexOf('<details class="advanced-routes"'))
    assert.equal((html.match(/id="role-materials.vision"/g)||[]).length,1)
    assert.deepEqual(rolesInGroup([role],['materials.']),[])
  })
  await check('Configured model is not presented as a completed PDF recognition pipeline',async()=>{
    const html=await renderToString(createSSRApp(Document,{role,scope,providers,models:[model],mutation:'',loading:false,
      resolution:{value:{provider_name:'测试连接',model:'vision-test',resolution_source:'global:materials.vision'},error:''}}))
    assert.match(html,/模型配置已就绪/);assert.match(html,/已接入单页核对/)
    assert.match(html,/上传不会自动发送整份 PDF/)
    assert.match(html,/专用 OCR 服务/)
  })
  await check('Image probe discloses synthetic input, cost and limited accuracy evidence',async()=>{
    const html=await renderToString(createSSRApp(Card,{model,busy:false,saveCapabilities:async()=>true,verifyModel:async()=>true}))
    assert.match(html,/检测文档识别能力/);assert.match(html,/不发送你的资料/)
    assert.match(html,/最多 3 次请求/);assert.match(html,/不保证公式、图表的识别质量/)
  })
  await check('No document-probe shortcut is shown on text-only models',async()=>{
    const text={...model,capabilities:{...model.capabilities,vision:{supported:false,status:'unsupported'}}}
    const html=await renderToString(createSSRApp(Card,{model:text,busy:false,saveCapabilities:async()=>true,verifyModel:async()=>true}))
    assert.doesNotMatch(html,/检测文档识别能力/)
  })
  console.log(`${count} document settings checks passed`)
} finally {await vite.close()}
