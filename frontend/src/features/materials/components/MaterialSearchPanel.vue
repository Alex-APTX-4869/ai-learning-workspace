<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { useMaterialSearch } from '../useMaterialSearch'
import { locationText } from '../labels'
import type { MaterialFile } from '../types'
import SourcePassageDialog from './SourcePassageDialog.vue'
const props=defineProps<{courseId:number;outlineVersionId:number|null;files:MaterialFile[]}>()
const query=ref(''), fileId=ref(''), pageText=ref<string|number>('')
const file=computed(()=>props.files.find(item=>item.id===fileId.value))
const page=computed(()=>String(pageText.value).trim() ? Number(pageText.value) : null)
const canSearch=computed(()=>!!query.value.trim() || !!(fileId.value && page.value))
const {result,searching,searchError,selected,source,reading,sourceError,search,read,closeSource}=useMaterialSearch(toRef(props,'courseId'),toRef(props,'outlineVersionId'))
watch(fileId,()=>pageText.value='')
function submit() {
  if(!canSearch.value || searching.value) return
  void search(query.value.trim(),fileId.value,page.value)
}
</script>
<template>
  <section class="source-search" aria-labelledby="source-search-title">
    <h3 id="source-search-title">查找资料原文</h3>
    <p class="hint">关键词检索 · 仅限当前版本已确认的范围 · 不调用 AI</p>
    <form @submit.prevent="submit">
      <div class="filters">
        <label>资料<select v-model="fileId"><option value="">全部已纳入资料</option><option v-for="item in files" :key="item.id" :value="item.id">{{item.filename}}</option></select></label>
        <label v-if="file?.suffix==='.pdf'">物理页码<input v-model="pageText" type="number" min="1" :max="file.page_count || 150" step="1" placeholder="可选" /></label>
      </div>
      <div class="query-row"><label>关键词<input v-model="query" maxlength="500" placeholder="例如：连接池、HTTPException、错误码" /></label><button class="button primary small" :disabled="!canSearch || searching">{{searching?'正在查找…':'查找'}}</button></div>
      <p v-if="file?.suffix==='.pdf'" class="hint">选定文件与页码后，可不填关键词直接查看该页；未纳入的页不会返回。</p>
    </form>
    <p v-if="searchError" role="alert" class="error-message">{{searchError}}</p>
    <div v-if="result" aria-live="polite">
      <p v-if="!result.scope_available" class="hint">当前版本没有确认的可检索资料。</p>
      <p v-else-if="!result.hits.length" class="hint">已确认范围内未找到匹配文字。可换用原文词语或指定页码；这不代表资料中一定没有相关概念，图片内文字也尚未识别。</p>
      <template v-else>
        <p class="hint">找到 {{result.total}} 个匹配片段，展示最相关的 {{result.hits.length}} 个。</p>
        <ol class="hits"><li v-for="hit in result.hits" :key="`${hit.file_id}:${hit.process_id}:${hit.element_id}:${hit.offset}`">
          <strong>{{hit.filename}}</strong><span class="location">{{locationText(hit.locator)}}</span>
          <p v-if="hit.locator.heading_path?.length" class="hint">{{hit.locator.heading_path.join(' / ')}}</p>
          <p class="excerpt">{{hit.excerpt}}</p>
          <button type="button" class="button secondary small" @click="read(hit)">查看原文与出处</button>
        </li></ol>
      </template>
    </div>
    <SourcePassageDialog v-if="selected" :hit="selected" :source="source" :loading="reading" :error="sourceError"
      @close="closeSource" @retry="read(selected)" @beginning="read(selected,0)" @more="source?.next_offset!==null && source?.next_offset!==undefined && read(selected,source.next_offset,true)" />
  </section>
</template>
<style scoped>
.source-search{border:1px solid var(--line);border-radius:12px;padding:22px;margin:22px 0;background:var(--surface);min-width:0;}h3{font-size:16px;}.hint{font-size:12px;color:var(--muted);line-height:1.8;margin:9px 0;}
.filters,.query-row{display:flex;gap:14px;align-items:end;margin-top:14px;}label{display:flex;flex-direction:column;gap:7px;font-size:12px;flex:1;min-width:0;}.filters label+label{flex:0 0 130px;}input,select{width:100%;min-width:0;}.query-row button{flex-shrink:0;min-height:42px;}
select{padding:11px 12px;border:1px solid var(--line);border-radius:9px;background:var(--soft);color:var(--ink);font:inherit;}
.hits{list-style:none;padding:0;}.hits li{border-top:1px solid var(--line);padding:18px 0;overflow-wrap:anywhere;}.hits strong{font-size:13px;}.location{display:block;font-size:12px;color:var(--muted);margin-top:6px;}.excerpt{white-space:pre-wrap;font-size:13px;line-height:1.9;margin:12px 0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:5;overflow:hidden;}
@media(max-width:640px){.source-search{padding:16px;}.filters{flex-wrap:wrap;}.filters label+label{flex:1;}.query-row{flex-wrap:wrap;}.query-row label{flex-basis:100%;}}
</style>
