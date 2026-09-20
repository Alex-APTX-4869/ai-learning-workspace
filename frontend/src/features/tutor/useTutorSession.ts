import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { errorMessage, HttpError } from '../../shared/api'
import { tutorApi } from './api'
import type { TutorAction, TutorSession } from './types'

export function useTutorSession(courseId: Ref<number>, outlineVersionId: Ref<number | null>, pointId: Ref<number>, contentVersionId: Ref<number>) {
  const session = ref<TutorSession | null>(null)
  const loading = ref(false)
  const sending = ref(false)
  const error = ref('')
  const busy = computed(() => loading.value || sending.value || !!session.value?.busy)
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let generation = 0
  // 网络结果不明时可重发同一编号，由服务器去重，避免重复扣费或翻两张。
  let uncertainAction: { sessionId: number; action: TutorAction } | null = null
  const retryable = ref(false)

  function stop() {
    generation += 1
    if (timer !== null) clearTimeout(timer)
    timer = null
    controller?.abort()
    controller = null
  }

  function accept(value: TutorSession, token: number) {
    if (token !== generation) return
    if (value.content_version_id !== contentVersionId.value || value.outline_version_id !== outlineVersionId.value) {
      error.value = '当前内容版本已更新，请重新打开知识点。'
      return
    }
    session.value = value
    if (value.busy) schedule(token)
  }

  function schedule(token: number, delay = 1000) {
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => void poll(token), delay)
  }

  async function poll(token: number) {
    if (!session.value || token !== generation) return
    try {
      const value = await tutorApi.session(session.value.id, controller?.signal)
      if (token !== generation) return
      error.value = ''
      accept(value, token)
    } catch (cause) {
      if (token !== generation) return
      error.value = `${errorMessage(cause)} 正在重新连接学习记录。`
      schedule(token, 3000)
    }
  }

  async function load() {
    stop()
    const token = generation
    controller = new AbortController()
    session.value = null
    uncertainAction = null
    retryable.value = false
    sending.value = false
    loading.value = true
    error.value = ''
    try {
      accept(await tutorApi.start(courseId.value, outlineVersionId.value, pointId.value, contentVersionId.value, controller.signal), token)
    } catch (cause) {
      if (token === generation) error.value = errorMessage(cause)
    } finally {
      if (token === generation) loading.value = false
    }
  }

  async function sendRequest(request: { sessionId: number; action: TutorAction }) {
    const token = generation
    sending.value = true
    error.value = ''
    try {
      const result = await tutorApi.action(request.sessionId, request.action, controller?.signal)
      if (token !== generation) return false
      uncertainAction = null
      retryable.value = false
      accept(result, token)
      return true
    } catch (cause) {
      if (token !== generation) return false
      error.value = errorMessage(cause)
      if (cause instanceof HttpError && cause.status < 500) {
        uncertainAction = null
        retryable.value = false
      } else {
        uncertainAction = request
        retryable.value = true
      }
      // 接口失败后先恢复服务器状态，避免按钮停在旧卡片。
      if (cause instanceof HttpError && cause.status === 409) await poll(token)
      return false
    } finally {
      if (token === generation) sending.value = false
    }
  }

  async function act(action: TutorAction['action'], fields: Partial<TutorAction> = {}) {
    if (busy.value || !session.value || retryable.value) return false
    return sendRequest({ sessionId: session.value.id, action: {
      ...fields, action, request_id: crypto.randomUUID(),
      revision: session.value.revision, card_id: session.value.current_card.id,
    } })
  }

  function retry() {
    if (!sending.value && uncertainAction) return sendRequest(uncertainAction)
    return Promise.resolve(false)
  }

  watch([courseId, outlineVersionId, pointId, contentVersionId], load, { immediate: true })
  onBeforeUnmount(stop)
  return { session, loading, sending, busy, error, retryable, act, retry, load }
}
