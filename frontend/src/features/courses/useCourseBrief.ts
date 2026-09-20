import { ref } from 'vue'
import { errorMessage, HttpError } from '../../shared/api'
import { coursesApi } from './api'
import type { CourseBrief } from './briefTypes'

export function useCourseBrief(courseId: number, outlineVersionId: number | null) {
  const brief = ref<CourseBrief | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  let requestVersion = 0

  async function load() {
    if (loading.value) return
    const version = ++requestVersion
    loading.value = true
    error.value = ''
    try {
      brief.value = await coursesApi.brief(courseId, outlineVersionId)
      loaded.value = true
    } catch (cause) {
      if (version !== requestVersion) return
      // 兼容旧课程及后端升级前的状态：没有确认档案不是页面错误。
      if (cause instanceof HttpError && cause.status === 404) {
        brief.value = null
        loaded.value = true
      } else {
        error.value = errorMessage(cause)
      }
    } finally {
      if (version === requestVersion) loading.value = false
    }
  }

  return { brief, loading, loaded, error, load }
}
