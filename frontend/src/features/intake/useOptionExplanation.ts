import { ref, onBeforeUnmount } from 'vue'
import { errorMessage } from '../../shared/api'
import { streamMarkdown } from '../../shared/stream'
import type { InterviewQuestion, QuestionOption } from './types'

type ExplanationRequest = {
  intakeId: number
  questionId: string
  option: QuestionOption
}

export function useOptionExplanation() {
  const panelOpen = ref(false)
  const selectedOption = ref<QuestionOption | null>(null)
  const explanation = ref('')
  const loading = ref(false)
  const error = ref('')
  const cache = new Map<string, string>()
  let controller: AbortController | null = null
  let lastRequest: ExplanationRequest | null = null
  let requestVersion = 0

  function cacheKey(intakeId: number, questionId: string, optionId: string) {
    return `${intakeId}:${questionId}:${optionId}`
  }

  async function load(request: ExplanationRequest) {
    controller?.abort()
    const currentVersion = ++requestVersion
    const { intakeId, questionId, option } = request
    const key = cacheKey(intakeId, questionId, option.id)
    lastRequest = request
    selectedOption.value = option
    panelOpen.value = true
    error.value = ''

    const saved = cache.get(key)
    if (saved) {
      explanation.value = saved
      loading.value = false
      return
    }

    explanation.value = ''
    loading.value = true
    controller = new AbortController()
    try {
      let result=''
      await streamMarkdown(`/course-intakes/${intakeId}/questions/${encodeURIComponent(questionId)}/options/${encodeURIComponent(option.id)}/explain-stream`,controller.signal,delta=>{
        result+=delta
        if(currentVersion===requestVersion) explanation.value=result
      })
      if(currentVersion===requestVersion) cache.set(key,result)
    } catch (cause) {
      if (currentVersion === requestVersion) error.value = errorMessage(cause)
    } finally {
      if (currentVersion === requestVersion) loading.value = false
    }
  }

  async function explain(intakeId: number, question: InterviewQuestion, option: QuestionOption) {
    await load({ intakeId, questionId: question.id, option })
  }

  async function retry() {
    if (!lastRequest || loading.value) return
    cache.delete(cacheKey(lastRequest.intakeId, lastRequest.questionId, lastRequest.option.id))
    await load(lastRequest)
  }

  function closePanel() {
    panelOpen.value = false
  }

  function reset() {
    controller?.abort()
    requestVersion += 1
    panelOpen.value = false
    selectedOption.value = null
    explanation.value = ''
    loading.value = false
    error.value = ''
    lastRequest = null
    cache.clear()
  }
  onBeforeUnmount(reset)

  return {
    panelOpen,
    selectedOption,
    explanation,
    loading,
    error,
    explain,
    retry,
    closePanel,
    reset,
  }
}
