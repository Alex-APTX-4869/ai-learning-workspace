<script setup lang="ts">
import { computed, nextTick, ref, toRef, watch } from 'vue'
import SafeMarkdown from '../../learning/components/SafeMarkdown.vue'
import CodeLabPanel from '../../learning/components/CodeLabPanel.vue'
import TutorExercise from './TutorExercise.vue'
import { useTutorSession } from '../useTutorSession'
import { stageLabels } from '../types'
import ContentSources from '../../learning/components/ContentSources.vue'
import type { MaterialEvidence } from '../../learning/types'
const props=defineProps<{courseId:number;outlineVersionId:number|null;pointId:number;contentVersionId:number;nextPointName?:string;materialEvidence?:MaterialEvidence|null}>()
const emit=defineEmits<{nextPoint:[];exit:[]}>()
const {session,loading,busy,error,retryable,act,retry,load}=useTutorSession(toRef(props,'courseId'),toRef(props,'outlineVersionId'),toRef(props,'pointId'),toRef(props,'contentVersionId'))
const drafts=ref<Record<string,string>>({})
const draft=computed({get:()=>drafts.value[current.value?.id||'']||'',set:(value:string)=>{drafts.value[current.value?.id||'']=value}})
const conversation=ref<HTMLElement|null>(null)
const blocked=computed(()=>busy.value||retryable.value)
const current=computed(()=>session.value?.current_card)
// 只显示当前卡片及它的问答；历史进度保留，上一张可回看。
const currentTurns=computed(()=>session.value?.turns.filter(turn=>turn.card_id===current.value?.id)||[])
const nextLabel=computed(()=>current.value?.kind==='exercise'&&!session.value?.response?'跳过这题':session.value?.card_index=== (session.value?.card_count||0)-1?'本知识点看完了':'下一张')
watch(()=>`${session.value?.id}:${current.value?.id}`,async()=>{
  await nextTick()
  conversation.value?.scrollTo({top:0})
})
watch(()=>currentTurns.value.map(turn=>`${turn.id}:${turn.status}`).join(','),async()=>{
  const scroller=conversation.value
  const nearBottom=scroller&&scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<120
  await nextTick()
  if(nearBottom) scroller?.scrollTo({top:scroller.scrollHeight,behavior:'smooth'})
})
async function send(message=draft.value) {
  if(!message.trim()||blocked.value)return
  if(await act('message',{message:message.trim()}))draft.value=''
}
function onEnter(event:KeyboardEvent) {
  if(!event.shiftKey&&!event.isComposing){event.preventDefault();void send()}
}
</script>
<template>
  <section class="tutor-panel" aria-label="讲师对话">
    <header class="conversation-header">
      <span id="tutor-chat-title" class="sr-only">讲师带学对话</span>
      <nav class="conversation-tabs" aria-label="卡片对话切换">
        <button v-for="(tab,index) in session?.card_tabs" :key="tab.id" type="button"
          :aria-pressed="tab.id===current?.id" :disabled="blocked" :title="tab.title"
          @click="tab.id!==current?.id && act('open',{target_card_id:tab.id})">{{index+1}}. {{tab.title}}</button>
      </nav>
      <button type="button" class="button secondary small exit-chat" @click="emit('exit')">退出讲课</button>
    </header>
    <div class="conversation" ref="conversation" role="log" aria-label="当前知识卡片与讲师问答" tabindex="0">
    <p v-if="loading" role="status"><span class="spinner" />正在接回学习进度…</p>
    <div v-if="error" class="tutor-error" role="alert">{{ error }}
      <button v-if="retryable" class="button secondary small" :disabled="busy" @click="retry">重试刚才的操作</button>
      <button v-else-if="!session" class="button secondary small" @click="load">重新连接</button>
    </div>
    <template v-if="session&&current">
          <article :key="current.id" class="knowledge-card">
            <header><span>讲师 · {{stageLabels[current.kind]}}</span><h3>{{current.title}}</h3></header>
            <div class="card-body">
              <SafeMarkdown v-if="current.body_markdown" :source="current.body_markdown" />
              <pre v-if="current.code"><code>{{current.code}}</code></pre>
              <TutorExercise v-if="current.exercise" :exercise="current.exercise" :response="session.response"
                :disabled="blocked"
                @submit="(selected,written)=>act('answer',{selected,written_answer:written})" />
              <CodeLabPanel v-if="current.lab" :lab="current.lab" />
              <ContentSources :key="current.id" :course-id="courseId" :outline-version-id="session.outline_version_id"
                :evidence="materialEvidence" :items="[current]" />
            </div>
          </article>
          <div v-for="turn in currentTurns" :key="turn.id" class="exchange">
            <div class="user-message"><small>你</small><p>{{turn.user_message}}</p></div>
            <div class="teacher-message"><small>讲师</small>
              <SafeMarkdown v-if="turn.reply_markdown" :source="turn.reply_markdown" />
              <p v-else-if="turn.error" class="tutor-error">{{turn.error}} <button :disabled="blocked" @click="send(turn.user_message||'')">重新提问</button></p>
              <p v-else role="status"><span class="spinner" />正在思考你的问题…</p>
            </div>
          </div>
    </template>
    </div>
      <div v-if="session&&current" class="composer-dock">
        <form class="chat-composer" @submit.prevent="send()">
          <label class="sr-only" for="tutor-question">向讲师提问</label>
          <textarea id="tutor-question" v-model="draft" :disabled="blocked" maxlength="6000" rows="2"
            placeholder="哪里没理解？可以请讲师从具体例子开始解释…" @keydown.enter="onEnter" />
          <div class="composer-actions">
            <button v-if="session.completed&&nextPointName" type="button" class="button secondary small" :disabled="blocked" @click="emit('nextPoint')">下一个知识点</button>
            <button v-else type="button" class="button secondary small" :disabled="blocked||session.completed" @click="act('next')">{{session.completed?'已浏览完毕':nextLabel}}</button>
            <button class="button primary small" :disabled="blocked||!draft.trim()">{{session.busy?'讲师回答中':'发送'}}</button>
          </div>
        </form>
      </div>
  </section>
</template>
<style scoped>
.tutor-panel{display:flex;flex-direction:column;flex:1;min-height:0;min-width:0;overflow:hidden;}
.conversation-header{display:flex;align-items:center;gap:12px;flex-shrink:0;padding:12px 18px;border-bottom:1px solid var(--line);}
.conversation-tabs{display:flex;gap:6px;flex:1;min-width:0;overflow-x:auto;}
.conversation-tabs button{flex-shrink:0;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:9px 12px;border:0;border-radius:8px;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer;}
.conversation-tabs button[aria-pressed=true]{background:var(--soft);color:var(--text);}
.exit-chat{flex-shrink:0;}
.path{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted);align-items:center;}.path .active{color:var(--accent);font-weight:600;}.path small{margin-left:auto;}
.welcome{font-size:12px;color:var(--muted);line-height:1.9;margin:16px 0;}
.conversation{flex:1;min-height:0;overflow-y:auto;overscroll-behavior-y:contain;padding:0 max(20px,calc((100% - 840px)/2)) 20px;scrollbar-gutter:stable;}
.knowledge-card{margin:20px 0;border:1px solid var(--line);border-radius:14px;background:var(--surface);}
.knowledge-card header{padding:18px 22px 12px;border-bottom:1px solid var(--line);}
.knowledge-card header span,.teacher-message>small,.user-message>small{font-size:11px;color:var(--muted);}
h3{font-size:19px;line-height:1.5;margin-top:7px;}.card-body{padding:20px 22px;}
.knowledge-card,.card-body{max-height:none;overflow:visible;}
pre{overflow-x:auto;white-space:pre;padding:14px;background:var(--soft);border-radius:8px;font-size:12px;line-height:1.8;}
.exchange{margin:20px 0;}.user-message{max-width:85%;margin-left:auto;padding:14px 18px;background:var(--soft);border-radius:13px;}
.user-message p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;font-size:14px;}
.teacher-message{padding:20px 0 0;}.teacher-message>small{display:block;margin-bottom:8px;}
.composer-dock{flex-shrink:0;background:var(--surface);border-top:1px solid var(--line);padding:10px max(20px,calc((100% - 840px)/2));}
.card-actions,.composer-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;}
.card-actions small,.composer-actions small{font-size:11px;color:var(--muted);}.chat-composer{margin:0;}
textarea{font-size:13px;resize:none;}.composer-actions{margin-top:8px;}.tutor-error{padding:12px;background:#fcf3ef;color:#945b42;line-height:1.8;font-size:12px;}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);}
@media(max-width:640px){.knowledge-card header,.card-body{padding:16px;}.card-actions small{display:none;}.user-message{max-width:94%;}h3{font-size:17px;}}
</style>
