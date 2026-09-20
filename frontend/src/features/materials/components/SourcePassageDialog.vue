<script setup lang="ts">
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import { materialsApi } from '../api'
import { locationText } from '../labels'
import type { SourceHit, SourcePassage } from '../types'
defineProps<{hit:SourceHit;source:SourcePassage|null;loading:boolean;error:string}>()
defineEmits<{close:[];retry:[];beginning:[];more:[]}>()
</script>
<template>
  <BaseDialog open wide labelledby="source-title" @close="$emit('close')">
    <section class="source-dialog">
      <header><div><h2 id="source-title">{{hit.filename}}</h2><p>{{locationText(hit.locator)}}<span v-if="hit.locator.heading_path?.length"> · {{hit.locator.heading_path.join(' / ')}}</span></p></div><button type="button" class="button secondary small" @click="$emit('close')">关闭原文</button></header>
      <div class="source-body">
        <p v-if="loading" role="status">正在读取原文…</p>
        <p v-if="error" role="alert">{{error}} <button type="button" class="button secondary small" :disabled="loading" @click="$emit('retry')">重试</button></p>
        <template v-if="source">
          <p class="note">{{source.locator.source_kind==='vision_transcription' ? '这是已人工核对并纳入当前版本的 AI 视觉转录，不是原文件的逐字真值；请结合原页核对。' : '这是已确认解析版本的提取文字，不是 AI 回答。'}}{{source.text_only?'未采用视觉转录的页面仅使用可提取文字，可能有识别缺口。':''}}</p>
          <p class="note">当前显示本段第 {{source.offset+1}}–{{source.offset+source.text.length}} 个字符，共 {{source.total_characters}} 个。</p>
          <button v-if="source.offset>0" type="button" class="button secondary small" :disabled="loading" @click="$emit('beginning')">从本段开头阅读</button>
          <pre class="source-text">{{source.text}}</pre>
          <button v-if="source.next_offset!==null" type="button" class="button secondary small" :disabled="loading" @click="$emit('more')">继续读取本段</button>
          <details v-if="source.preview"><summary>查看对应原页 / 图片</summary><img loading="lazy" :src="materialsApi.artifact(source.batch_id,source.file_id,source.process_id,source.preview)" :alt="`${source.filename} · ${locationText(source.locator)}`" /></details>
          <p v-else class="note">该段没有可用原页预览；可在下方资料记录中下载原文件核对。</p>
        </template>
      </div>
    </section>
  </BaseDialog>
</template>
<style scoped>
.source-dialog{height:100%;display:flex;flex-direction:column;min-height:0;}header{padding:20px 24px;display:flex;gap:16px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);flex-shrink:0;}header>div{min-width:0;}h2{font-size:18px;overflow-wrap:anywhere;}header p,.note{color:var(--muted);font-size:12px;line-height:1.8;margin-top:8px;}header button{flex-shrink:0;}.source-body{flex:1;min-height:0;overflow-y:auto;padding:24px;}.source-text{font:inherit;font-size:14px;line-height:2;white-space:pre-wrap;overflow-wrap:anywhere;margin:18px 0;}details{margin-top:22px;}summary{cursor:pointer;font-size:13px;}img{display:block;max-width:100%;height:auto;margin-top:16px;}
@media(max-width:640px){header,.source-body{padding:16px;}h2{font-size:16px;}}
</style>
