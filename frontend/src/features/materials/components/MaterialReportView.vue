<script setup lang="ts">
import { ref, watch } from 'vue'
import { materialsApi } from '../api'
import { issueLabel, locationText } from '../labels'
import { errorMessage } from '../../../shared/api'
import type { MaterialFile, MaterialReport } from '../types'
const props = defineProps<{batchId: string; file: MaterialFile}>()
const report = ref<MaterialReport | null>(null)
const error = ref('')
const loading = ref(false)
const offset = ref(0)
let version = 0
async function load(next=0) {
  if (!props.file.process_id) return
  const current = ++version
  loading.value = true
  error.value = ''
  try {
    const result = await materialsApi.report(props.batchId, props.file.id, props.file.process_id, next)
    if (current === version) { report.value = result; offset.value = next }
  } catch (cause) { if (current === version) error.value = errorMessage(cause) }
  finally { if (current === version) loading.value = false }
}
watch(() => props.file.process_id, () => load(), {immediate: true})
</script>
<template>
  <div class="report-view">
    <a :href="materialsApi.original(batchId, file.id)">下载原文件核对</a>
    <p v-if="loading" role="status">正在读取解析报告…</p>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="load()">重试</button></p>
    <template v-if="report">
      <details v-if="report.issues.length">
        <summary>{{ report.issues.length }} 处识别说明</summary>
        <ul><li v-for="(issue, i) in report.issues" :key="i">{{ locationText(issue.locator) }}：{{ issueLabel[issue.code] || '此处需要核对原文' }}</li></ul>
      </details>
      <div class="extracted-text">
        <article v-for="element in report.elements" :key="element.id">
          <small>{{ locationText(element.locator) }}</small>
          <p>{{ element.text || '此处为图片或公式，尚未转换为可用文字。' }}</p>
          <details v-if="element.preview && file.process_id"><summary>查看原页</summary>
            <img :src="materialsApi.artifact(batchId,file.id,file.process_id,element.preview)" :alt="locationText(element.locator)" loading="lazy" />
          </details>
        </article>
      </div>
      <div class="pagination" v-if="report.element_count > 30">
        <button type="button" :disabled="loading || offset === 0" @click="load(offset-30)">上一组</button>
        <span>{{ offset+1 }}–{{ Math.min(offset+30,report.element_count) }} / {{ report.element_count }}</span>
        <button type="button" :disabled="loading || offset+30 >= report.element_count" @click="load(offset+30)">下一组</button>
      </div>
    </template>
  </div>
</template>
<style scoped>
.report-view { margin-top: 14px; font-size: 12px; line-height: 1.8; }
.report-view a { color: var(--accent); } summary { cursor: pointer; padding: 8px 0; }
.extracted-text { max-height: 420px; overflow: auto; margin-top: 10px; border-top: 1px solid var(--line); }
article { padding: 12px 0; border-bottom: 1px solid var(--line); } small { color: var(--muted); }
article p { white-space: pre-wrap; overflow-wrap: anywhere; } img { max-width: 100%; height: auto; }
ul { padding-left: 20px; max-height: 160px; overflow: auto; }.pagination { display: flex; justify-content: space-between; gap: 8px; padding-top: 10px; }
</style>
