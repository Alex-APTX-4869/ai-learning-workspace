<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { errorMessage } from '../../../shared/api'
import { materialsApi } from '../api'
import type { MaterialBatch } from '../types'
import MaterialFileCard from './MaterialFileCard.vue'
import MaterialSearchPanel from './MaterialSearchPanel.vue'
const props = defineProps<{courseId: number; outlineVersionId: number|null}>()
const batch = ref<MaterialBatch|null>(null)
const loading = ref(false)
const error = ref('')
let revision = 0
async function load() {
  const current = ++revision
  loading.value=true; error.value=''; batch.value=null
  try { const value=await materialsApi.forCourse(props.courseId,props.outlineVersionId); if(current===revision) batch.value=value }
  catch(cause) { if(current===revision) error.value=errorMessage(cause) }
  finally { if(current===revision) loading.value=false }
}
watch(()=>[props.courseId,props.outlineVersionId],load,{immediate:true})
onBeforeUnmount(()=>revision++)
</script>

<template>
  <section class="materials-panel">
    <div class="materials-heading">
      <h2>课程参考资料</h2>
      <p>创建课程时确认的资料与标注保留在这里，原文件和解析报告可以随时回看。</p>
    </div>
    <p v-if="loading" role="status">正在读取资料…</p>
    <div v-else-if="error" role="alert">{{ error }} <button class="button secondary small" @click="load">重试</button></div>
    <template v-else-if="batch">
      <p class="materials-note">{{ batch.completeness==='partial' ? '本次仅使用部分资料' : '用户已确认：本次资料已全部上传' }} · 已固定的资料范围</p>
      <MaterialSearchPanel :key="`${courseId}:${outlineVersionId}`" :course-id="courseId" :outline-version-id="outlineVersionId" :files="batch.files.filter(file=>file.included)" />
      <MaterialFileCard v-for="file in batch.files" :key="file.id" :batch-id="file.batch_id || batch.id" :file="file" disabled read-only />
      <details v-for="file in batch.context?.files" :key="file.file_id">
        <summary>{{ file.filename }} · 分析摘要</summary>
        <p class="summary">{{ file.analysis.summary }}</p>
        <ul><li v-for="gap in file.analysis.gaps" :key="gap">{{ gap }}</li></ul>
      </details>
      <p class="materials-note">搜索只查当前版本固定的提取文字和已采用视觉转录，不调用 AI。内容制作可读取这些来源，讲师沿用制作时的来源片段；新的识别不会自动更新旧课程。向量检索和讲师主动再次查证尚未接入；摘要不等于完整原文。</p>
    </template>
    <p v-else class="upload-placeholder materials-note">当前目录版本没有关联参考资料。可以在创建课程时上传，或通过“增加章节”为新章节附上资料。</p>
  </section>
</template>

<style scoped>
.materials-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 32px;
}
.materials-heading h2 {
  font-size: 20px;
  margin-bottom: 9px;
}
.materials-heading p,
.materials-note {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
}
.upload-placeholder {
  border: 1px dashed #cad5df;
  border-radius: 12px;
  padding: 38px 20px;
  text-align: center;
  margin: 28px 0 20px;
  background: var(--soft);
}
.upload-placeholder h3 {
  font-size: 16px;
  margin: 16px 0 10px;
}
.upload-placeholder p {
  font-size: 13px;
  color: var(--muted);
  max-width: 370px;
  margin: 0 auto 23px;
  line-height: 1.8;
}
.upload-placeholder .empty-icon {
  margin: auto;
}
.materials-note {
  font-size: 12px;
  margin-top: 16px;
}
details {margin-top:16px;border-top:1px solid var(--line);padding-top:14px;font-size:13px;line-height:1.9;}
summary {cursor:pointer;}.summary {white-space:pre-wrap;margin-top:12px;}ul {padding-left:20px;}
@media (max-width: 640px) {
  .materials-panel {
    padding: 22px;
  }
}
</style>
