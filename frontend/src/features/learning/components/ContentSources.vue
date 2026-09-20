<script setup lang="ts">
import { toRef, watch } from 'vue'
import type { MaterialEvidence, SourceAttribution } from '../types'
import { locationText } from '../../materials/labels'
import { useMaterialSearch } from '../../materials/useMaterialSearch'
import SourcePassageDialog from '../../materials/components/SourcePassageDialog.vue'

const props = defineProps<{
  courseId: number
  outlineVersionId: number | null
  evidence?: MaterialEvidence | null
  items: Array<SourceAttribution & { title: string }>
}>()
const { selected, source, reading, sourceError, read, closeSource } = useMaterialSearch(
  toRef(props, 'courseId'), toRef(props, 'outlineVersionId'),
)
watch(() => props.evidence, closeSource)
function citations(ids: string[] = []) {
  return props.evidence?.sources.filter(item => ids.includes(item.id)) || []
}
</script>
<template>
  <details v-if="evidence?.method === 'keyword'" class="content-sources">
    <summary>资料出处与补充说明</summary>
    <p>引用指向生成时读取的原文；AI 改写仍可能有误，可点击核对。PDF 页码为文件物理页码。</p>
    <section v-for="(item, index) in items" :key="index">
      <strong>{{ item.title }}</strong>
      <span>{{ item.source_kind === 'source_based' ? '依据资料改写 / 应用' : 'AI 补充内容，不是资料原文' }}</span>
      <button v-for="citation in citations(item.source_ids)" :key="citation.id" type="button"
        class="source-link" @click="read(citation)">
        [{{ citation.id }}] {{ citation.filename }} · {{ locationText(citation.locator) }}
      </button>
    </section>
    <p v-if="evidence.sources.some(item => item.text_only)">仅使用可提取文字；图片、图表和公式可能未完整识别。</p>
  </details>
  <SourcePassageDialog v-if="selected" :hit="selected" :source="source" :loading="reading" :error="sourceError"
    @close="closeSource" @retry="read(selected)" @beginning="read(selected, 0)"
    @more="source?.next_offset != null && read(selected, source.next_offset, true)" />
</template>
<style scoped>
.content-sources{margin:20px 0;font-size:12px;line-height:1.8;color:var(--muted);overflow-wrap:anywhere;}
summary{cursor:pointer;color:var(--accent);}p{margin:10px 0;}section{margin:12px 0;}strong,span{display:block;}strong{color:var(--text);font-weight:500;}
.source-link{display:block;text-align:left;background:none;border:0;color:var(--accent);font:inherit;padding:4px 0;cursor:pointer;overflow-wrap:anywhere;}
</style>
