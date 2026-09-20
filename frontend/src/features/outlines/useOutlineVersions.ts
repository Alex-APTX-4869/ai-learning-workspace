import { onBeforeUnmount, ref } from 'vue'
import { errorMessage, HttpError } from '../../shared/api'
import { outlineVersionsApi } from './api'
import type {
  OutlineChapter,
  OutlineGenerationInput,
  OutlineStreamEvent,
  OutlineVersion,
} from './types'
import type { Course } from '../courses/types'

export function useOutlineVersions(courseId: number) {
  const versions = ref<OutlineVersion[]>([])
  const selectedVersion = ref<OutlineVersion | null>(null)
  const draftChapters = ref<OutlineChapter[]>([])
  const loading = ref(false)
  const selectingId = ref<number | null>(null)
  const generating = ref(false)
  const loadError = ref('')
  const selectionError = ref('')
  const generationError = ref('')
  const generationStatus = ref('')
  const generationSaved = ref(false)
  let controller: AbortController | null = null

  function rememberVersion(version: OutlineVersion) {
    versions.value = version.selected
      ? versions.value.map((item) => ({ ...item, selected: item.id === version.id }))
      : [...versions.value]
    const index = versions.value.findIndex((item) => item.id === version.id)
    if (index < 0) versions.value.unshift(version)
    else versions.value[index] = version
    if (version.selected) selectedVersion.value = version
  }

  async function load() {
    if (loading.value) return
    loading.value = true
    loadError.value = ''
    try {
      versions.value = await outlineVersionsApi.list(courseId)
      const included = versions.value.find((version) => version.selected) ?? null
      if (included) {
        selectedVersion.value = included
      } else {
        try {
          const selected = await outlineVersionsApi.selected(courseId)
          selectedVersion.value = selected
          if (!versions.value.some((version) => version.id === selected.id)) {
            versions.value.unshift(selected)
          }
        } catch (cause) {
          if (!(cause instanceof HttpError) || cause.status !== 404) throw cause
          selectedVersion.value = null
        }
      }
    } catch (cause) {
      loadError.value = errorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function select(versionId: number): Promise<Course | null> {
    if (selectingId.value !== null || generating.value || selectedVersion.value?.id === versionId)
      return null
    selectingId.value = versionId
    selectionError.value = ''
    try {
      const activated = await outlineVersionsApi.activate(courseId, versionId)
      if (activated.course.outline_version_id !== versionId) {
        throw new Error('后端没有返回刚刚选择的目录版本。')
      }
      rememberVersion(activated.version)
      return activated.course
    } catch (cause) {
      // POST 的响应可能丢失；先向服务器对账，避免选择器和目录各显示一个版本。
      try {
        const current = await outlineVersionsApi.selected(courseId)
        if (current.id === versionId) {
          const course = await outlineVersionsApi.course(courseId, versionId)
          rememberVersion(current)
          return course
        }
        rememberVersion(current)
      } catch {
        // 保留最初的、最接近用户操作的错误。
      }
      selectionError.value = errorMessage(cause)
      return null
    } finally {
      selectingId.value = null
    }
  }

  function receive(event: OutlineStreamEvent) {
    if (event.type === 'start') {
      generationStatus.value = '模型已开始规划课程结构'
      return
    }
    if (event.type === 'chapter') {
      const next = [...draftChapters.value]
      next[event.chapter.index] = { name: event.chapter.name, sections: next[event.chapter.index]?.sections || [] }
      draftChapters.value = next
      generationStatus.value = `已生成 ${next.filter(Boolean).length} 个章节`
      return
    }
    if (event.type === 'section') {
      const next = [...draftChapters.value]
      const chapter = next[event.section.chapter_index] ?? {
        name: `章节 ${event.section.chapter_index + 1}`,
        sections: [],
      }
      const sections = [...chapter.sections]
      sections[event.section.index] = { name: event.section.name }
      next[event.section.chapter_index] = { ...chapter, sections }
      draftChapters.value = next
      const sectionCount = next.reduce((sum, item) => sum + (item?.sections.length ?? 0), 0)
      generationStatus.value = `正在完善结构 · ${next.filter(Boolean).length} 章 ${sectionCount} 小节`
      return
    }
    if (event.type === 'completed') {
      rememberVersion(event.version)
      generationSaved.value = true
      generationStatus.value = event.version.selected
        ? `大纲版本 V${event.version.version_number} 已保存并设为当前版本`
        : `大纲版本 V${event.version.version_number} 已保存，可从版本列表切换`
      return
    }
    throw new Error(event.detail || '大纲生成没有完成。')
  }

  async function generate(input: OutlineGenerationInput) {
    if (generating.value) return false
    controller?.abort()
    controller = new AbortController()
    generating.value = true
    generationError.value = ''
    generationStatus.value = '正在连接模型'
    generationSaved.value = false
    draftChapters.value = []
    let completed = false
    try {
      await outlineVersionsApi.stream(
        courseId,
        input,
        (event) => {
          receive(event)
          if (event.type === 'completed') completed = true
        },
        controller.signal,
      )
      if (!completed) throw new Error('连接已经结束，但后端没有确认大纲保存成功。')
      await load()
      return true
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        generationStatus.value = '已取消生成，当前大纲版本没有改变'
      } else {
        generationError.value = errorMessage(cause)
      }
      return false
    } finally {
      generating.value = false
      controller = null
    }
  }

  function cancel() {
    if (!controller || controller.signal.aborted) return
    generationStatus.value = '正在取消生成…'
    controller.abort()
  }

  function clearGeneration() {
    if (generating.value) return
    draftChapters.value = []
    generationError.value = ''
    generationStatus.value = ''
    generationSaved.value = false
  }

  onBeforeUnmount(cancel)

  return {
    versions,
    selectedVersion,
    draftChapters,
    loading,
    selectingId,
    generating,
    loadError,
    selectionError,
    generationError,
    generationStatus,
    generationSaved,
    load,
    select,
    generate,
    cancel,
    clearGeneration,
  }
}
