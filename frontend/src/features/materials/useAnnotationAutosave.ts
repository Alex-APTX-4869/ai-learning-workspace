import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { errorMessage } from '../../shared/api'
import type { Annotation, MaterialFile } from './types'

export type AnnotationDraft = Pick<MaterialFile, 'annotations' | 'included' | 'text_only_accepted'>
export const annotationDraft = (file: AnnotationDraft): AnnotationDraft => ({
  annotations: file.annotations.map(a => ({...a})),
  included: file.included, text_only_accepted: file.text_only_accepted,
})
export const annotationKey = (file: AnnotationDraft) => JSON.stringify(annotationDraft(file))

export function annotationProblem(draft: AnnotationDraft, file: MaterialFile): string {
  if (!draft.annotations.length || draft.annotations.length > 30) return '请保留 1–30 条标注。'
  if (draft.annotations.reduce((n, a) => n + a.note.length + a.chapter.length, 0) > 6000) return '标注合计不能超过 6000 字。'
  for (const a of draft.annotations) {
    if (a.role === 'chapter' && !a.chapter.trim()) return '请填写所属章节，填完后会自动保存。'
    if ((a.page_start === null) !== (a.page_end === null)) return '请同时填写开始页和结束页，或都留空。'
    if (a.page_start !== null && (file.suffix !== '.pdf' || !file.page_count ||
      !Number.isInteger(a.page_start) || !Number.isInteger(a.page_end) ||
      a.page_start < 1 || a.page_end! < a.page_start || a.page_end! > file.page_count)) return '请填写有效的 PDF 页码范围。'
  }
  return ''
}

// 服务端是已保存状态的依据；浏览器仅暂存未完成/失败的编辑，不自动确认识别范围。
export function useAnnotationAutosave(options: {
  file: () => MaterialFile; batchId: string; disabled: () => boolean; readOnly: () => boolean
  save: (file: MaterialFile, draft: AnnotationDraft) => Promise<void>
  dirty: (value: boolean) => void
  delay?: number
}) {
  const annotations = ref<Annotation[]>([]), included = ref(true), textOnly = ref(false)
  const dirty = ref(false), saving = ref(false), failure = ref(''), cacheWarning = ref('')
  const cacheKey = `learning-space.annotation-draft:${options.batchId}:${options.file().id}`
  let base = '', sequence = 0, disposed = false, restored = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const draft = (): AnnotationDraft => ({annotations: annotations.value, included: included.value, text_only_accepted: textOnly.value})
  const problem = computed(() => dirty.value ? annotationProblem(draft(), options.file()) : '')
  function mark(value: boolean) { dirty.value = value; options.dirty(value) }
  function persist() {
    try { localStorage.setItem(cacheKey, JSON.stringify({base, draft: annotationDraft(draft())})); cacheWarning.value = '' }
    catch { cacheWarning.value = '浏览器无法暂存编辑；保存完成前请勿关闭页面。' }
  }
  function clearCache(expected?: string) {
    try {
      const cached = JSON.parse(localStorage.getItem(cacheKey) || 'null')
      // 关闭后重新打开并继续编辑时，旧请求不能删除新页面的草稿。
      if (expected && cached && annotationKey(cached.draft) !== expected) return
      localStorage.removeItem(cacheKey)
    } catch { /* 服务端保存不受影响 */ }
  }
  function adopt(file: AnnotationDraft) {
    annotations.value = file.annotations.map(a => ({...a}))
    included.value = file.included; textOnly.value = file.text_only_accepted
  }
  function schedule() {
    clearTimeout(timer)
    if (!disposed && dirty.value && !saving.value && !options.disabled() && !options.readOnly() && !failure.value && !problem.value)
      timer = setTimeout(flush, options.delay ?? 650)
  }
  function changed() {
    if (!dirty.value) base = annotationKey(options.file())
    sequence++; mark(true); failure.value = ''; persist(); schedule()
  }
  async function flush() {
    clearTimeout(timer)
    if (disposed || !dirty.value || saving.value || options.disabled() || options.readOnly() || problem.value) return
    if (base !== annotationKey(options.file())) {
      failure.value = '已保存标注发生变化，未覆盖。请先核对或采用已保存标注。'; return
    }
    const sent = annotationDraft(draft()), sentSequence = sequence
    const source = {...options.file(), ...annotationDraft(options.file())}
    saving.value = true; failure.value = ''
    try {
      await options.save(source, sent)
      base = annotationKey(sent)
      if (sequence === sentSequence) { mark(false); clearCache(annotationKey(sent)); cacheWarning.value = '' }
      else if (!disposed) persist() // 请求途中继续输入时，只确认已发出的快照，不清除新编辑。
    } catch (cause) { failure.value = errorMessage(cause); if (!disposed) persist() }
    finally { saving.value = false; schedule() }
  }
  function useSaved() { clearTimeout(timer); adopt(options.file()); base = annotationKey(options.file()); failure.value = ''; cacheWarning.value = ''; mark(false); clearCache() }
  watch(() => options.file().revision, () => {
    if (!dirty.value) { adopt(options.file()); base = annotationKey(options.file()) }
    if (!restored) {
      restored = true
      if (!options.readOnly()) {
        try {
          const saved = JSON.parse(localStorage.getItem(cacheKey) || 'null')
          if (saved && typeof saved.base === 'string' && typeof saved.draft?.included === 'boolean' && typeof saved.draft?.text_only_accepted === 'boolean' &&
            Array.isArray(saved.draft.annotations) && saved.draft.annotations.every((a: Annotation) =>
              ['auto','chapter','overview','reference'].includes(a.role) && typeof a.chapter === 'string' && typeof a.note === 'string')) {
            if (annotationKey(saved.draft) === base) clearCache()
            else { adopt(saved.draft); base = saved.base; mark(true); schedule() }
          }
        } catch { cacheWarning.value = '无法恢复本地标注草稿，请核对当前内容。' }
      }
    }
  }, {immediate: true})
  watch(options.disabled, schedule)
  onBeforeUnmount(() => { disposed = true; clearTimeout(timer); if (dirty.value) persist() })
  return {annotations, included, textOnly, dirty, saving, failure, cacheWarning, problem, changed, flush, useSaved}
}
