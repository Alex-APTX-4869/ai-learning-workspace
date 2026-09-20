import assert from 'node:assert/strict'
import {createServer} from 'vite'
import {createSSRApp} from 'vue'
import {renderToString} from '@vue/server-renderer'
const vite = await createServer({server:{middlewareMode:true,watch:null},appType:'custom'})
try {
  const {default:Question} = await vite.ssrLoadModule('/src/features/intake/components/IntakeQuestionStep.vue')
  for (const count of [2,6,27]) {
    const question = {id:'q',number:1,text:'只确认额外范围',purpose:'确认增量',baseline:'基础与练习仍保留',
      options:Array.from({length:count},(_,i)=>({id:`o${i}`,title:`方向 ${i}`,description:'选择含义',recommended:i===0}))}
    const html=await renderToString(createSSRApp(Question,{question,total:2,selectedId:null,customSelected:false,customAnswer:'',busy:false,explanationBusy:false}))
    assert.equal((html.match(/type="radio"/g)||[]).length,count+1)
    assert.ok(html.includes('共同前提：基础与练习仍保留'))
    assert.equal((html.match(/class="option-recommended"/g)||[]).length,1)
    if(count===27)assert.ok(html.includes('AA.'))
    console.log(`PASS ${count} dynamic options, shared baseline, one recommendation, custom input`)
  }
} finally {await vite.close()}
