import { computed, onBeforeUnmount, ref } from 'vue'
import { errorMessage, HttpError } from '../../shared/api'
import { learningApi } from './api'
import {
  isActiveLearningJob,
  learningJobStatusText,
  type LearningJob,
  type PointContentVersion,
} from './types'

const POLL_INTERVAL_MS = 1200
const RETRY_INTERVAL_MS = 2600

export function usePointContent() {
  const content = ref<PointContentVersion | null>(null)
  const job = ref<LearningJob | null>(null)
  const loading = ref(false)
  const starting = ref(false)
  const cancelling = ref(false)
  const loadError = ref('')
  const actionError = ref('')

  const contentCache = new Map<string, PointContentVersion>()
  const jobCache = new Map<string, LearningJob>()
  let activeCourseId: number | null = null
  let activeOutlineVersionId: number | null = null
  let activePointId: number | null = null
  let operation = 0
  let timer: number | null = null
  let controller: AbortController | null = null

  const active = computed(() => isActiveLearningJob(job.value))
  const statusText = computed(() => learningJobStatusText(job.value))

  function key(courseId: number, outlineId: number | null, pointId: number) {
    return `${courseId}:${outlineId ?? 'legacy'}:${pointId}`
  }

  function clearTimer() {
    if (timer !== null) window.clearTimeout(timer)
    timer = null
  }

  function isCurrent(courseId: number, outlineId: number | null, pointId: number, token: number) {
    return (
      token === operation &&
      courseId === activeCourseId &&
      outlineId === activeOutlineVersionId &&
      pointId === activePointId
    )
  }

  async function loadContent(
    courseId: number,
    outlineId: number | null,
    pointId: number,
    token: number,
    { initial = false }: { initial?: boolean } = {},
  ) {
    if (initial) loading.value = !content.value
    loadError.value = ''
    try {
      const result = await learningApi.content(courseId, outlineId, pointId, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token)) return false
      if (result.outline_version_id !== outlineId) throw new Error('后端返回了另一目录版本的内容。')
      contentCache.set(key(courseId, outlineId, pointId), result)
      content.value = result
      return true
    } catch (cause) {
      if (!isCurrent(courseId, outlineId, pointId, token)) return false
      if (cause instanceof HttpError && cause.status === 404) {
        if (initial) content.value = null
        else loadError.value = '生成已完成，但内容暂时无法读取。请稍后重新加载。'
        return false
      }
      loadError.value = errorMessage(cause)
      return false
    } finally {
      if (isCurrent(courseId, outlineId, pointId, token)) loading.value = false
    }
  }

  function schedulePoll(
    courseId: number,
    outlineId: number | null,
    pointId: number,
    jobId: number,
    token: number,
    delay = POLL_INTERVAL_MS,
  ) {
    clearTimer()
    if (!isCurrent(courseId, outlineId, pointId, token)) return
    timer = window.setTimeout(() => {
      void poll(courseId, outlineId, pointId, jobId, token)
    }, delay)
  }

  async function poll(courseId: number, outlineId: number | null, pointId: number, jobId: number, token: number) {
    if (!isCurrent(courseId, outlineId, pointId, token)) return
    try {
      const next = await learningApi.job(jobId, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token) || cancelling.value) return
      if (next.outline_version_id !== outlineId) throw new Error('任务属于另一目录版本。')
      jobCache.set(key(courseId, outlineId, pointId), next)
      job.value = next
      actionError.value = ''
      if (isActiveLearningJob(next)) {
        schedulePoll(courseId, outlineId, pointId, jobId, token)
      } else if (next.status === 'ready') {
        await loadContent(courseId, outlineId, pointId, token)
      }
    } catch (cause) {
      if (!isCurrent(courseId, outlineId, pointId, token) || cancelling.value) return
      actionError.value = `${errorMessage(cause)} 将自动继续检查进度。`
      schedulePoll(courseId, outlineId, pointId, jobId, token, RETRY_INTERVAL_MS)
    }
  }

  async function loadActiveJob(courseId: number, outlineId: number | null, pointId: number, token: number) {
    try {
      const found = await learningApi.activeJob(courseId, outlineId, pointId, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token)) return
      const cacheKey = key(courseId, outlineId, pointId)
      if (found) jobCache.set(cacheKey, found)
      else jobCache.delete(cacheKey)
      job.value = found
      if (isActiveLearningJob(found)) schedulePoll(courseId, outlineId, pointId, found!.id, token, 0)
    } catch (cause) {
      if (isCurrent(courseId, outlineId, pointId, token)) {
        actionError.value = `生成进度暂时无法读取：${errorMessage(cause)}`
      }
    }
  }

  async function selectPoint(courseId: number, outlineId: number | null, pointId: number) {
    operation += 1
    const token = operation
    activeCourseId = courseId
    activeOutlineVersionId = outlineId
    activePointId = pointId
    // 旧知识点的 POST 即使随后返回，也不能把新知识点留在“启动中”。
    starting.value = false
    cancelling.value = false
    clearTimer()
    controller?.abort()
    controller = new AbortController()
    loadError.value = ''
    actionError.value = ''

    const cacheKey = key(courseId, outlineId, pointId)
    content.value = contentCache.get(cacheKey) ?? null
    const cachedJob = jobCache.get(cacheKey) ?? null
    job.value = cachedJob
    await Promise.all([
      loadContent(courseId, outlineId, pointId, token, { initial: true }),
      loadActiveJob(courseId, outlineId, pointId, token),
    ])
  }

  async function startJob() {
    const courseId = activeCourseId
    const outlineId = activeOutlineVersionId
    const pointId = activePointId
    const token = operation
    if (
      courseId === null ||
      pointId === null ||
      starting.value ||
      cancelling.value ||
      active.value
    )
      return

    starting.value = true
    actionError.value = ''
    try {
      const next = await learningApi.startContentJob(courseId, outlineId, pointId, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token)) return
      jobCache.set(key(courseId, outlineId, pointId), next)
      job.value = next
      if (isActiveLearningJob(next)) {
        schedulePoll(courseId, outlineId, pointId, next.id, token, 0)
      } else if (next.status === 'ready') {
        await loadContent(courseId, outlineId, pointId, token)
      }
    } catch (cause) {
      if (isCurrent(courseId, outlineId, pointId, token)) actionError.value = errorMessage(cause)
    } finally {
      if (isCurrent(courseId, outlineId, pointId, token)) starting.value = false
    }
  }

  async function cancelJob() {
    const current = job.value
    const courseId = activeCourseId
    const outlineId = activeOutlineVersionId
    const pointId = activePointId
    const token = operation
    if (
      !current ||
      (!isActiveLearningJob(current) && current.status !== 'needs_attention') ||
      courseId === null ||
      pointId === null ||
      cancelling.value
    )
      return

    cancelling.value = true
    actionError.value = ''
    clearTimer()
    try {
      const stopped = await learningApi.cancelJob(current.id, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token)) return
      jobCache.set(key(courseId, outlineId, pointId), stopped)
      job.value = stopped
    } catch (cause) {
      if (isCurrent(courseId, outlineId, pointId, token)) {
        actionError.value = errorMessage(cause)
        schedulePoll(courseId, outlineId, pointId, current.id, token)
      }
    } finally {
      if (isCurrent(courseId, outlineId, pointId, token)) cancelling.value = false
    }
  }

  async function retryJob() {
    const current = job.value
    const courseId = activeCourseId
    const outlineId = activeOutlineVersionId
    const pointId = activePointId
    const token = operation
    if (!current || current.status !== 'needs_attention' || courseId === null || pointId === null || starting.value) return
    starting.value = true
    actionError.value = ''
    try {
      const next = await learningApi.retryJob(current.id, controller?.signal)
      if (!isCurrent(courseId, outlineId, pointId, token)) return
      jobCache.set(key(courseId, outlineId, pointId), next)
      job.value = next
      schedulePoll(courseId, outlineId, pointId, next.id, token, 0)
    } catch (cause) {
      if (isCurrent(courseId, outlineId, pointId, token)) actionError.value = errorMessage(cause)
    } finally {
      if (isCurrent(courseId, outlineId, pointId, token)) starting.value = false
    }
  }

  function reload() {
    if (activeCourseId !== null && activePointId !== null) {
      void selectPoint(activeCourseId, activeOutlineVersionId, activePointId)
    }
  }

  function stop() {
    // 只停止这个页面的请求与轮询，不向后端发送 cancel。
    // 因此关闭弹窗、切换知识点或离开页面都不会中断生成。
    operation += 1
    activeCourseId = null
    activeOutlineVersionId = null
    activePointId = null
    loading.value = false
    starting.value = false
    cancelling.value = false
    clearTimer()
    controller?.abort()
    controller = null
  }

  onBeforeUnmount(stop)

  return {
    content,
    job,
    loading,
    starting,
    cancelling,
    loadError,
    actionError,
    active,
    statusText,
    selectPoint,
    startJob,
    cancelJob,
    retryJob,
    reload,
    stop,
  }
}
