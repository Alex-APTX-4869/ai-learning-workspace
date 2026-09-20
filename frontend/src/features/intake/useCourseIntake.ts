import { ref, shallowRef } from 'vue'
import { errorMessage, HttpError } from '../../shared/api'
import type { Course } from '../courses/types'
import { intakeApi } from './api'
import type { IntakePhase, IntakeRead } from './types'

type RetryAction = () => Promise<void>
const ACTIVE_INTAKE_KEY = 'learning-space.active-course-intake'
const SKIPPED_INTAKE_KEY = 'learning-space.skipped-course-intake'

export function useCourseIntake() {
  const phase = ref<IntakePhase>('start')
  const initialName = ref('')
  const initialIntro = ref('')
  const session = ref<IntakeRead | null>(null)
  const selectedDepthId = ref<string | null>(null)
  const customDepth = ref(false)
  const customQuestionCount = ref(6)
  const selectedOptionId = ref<string | null>(null)
  const customAnswerSelected = ref(false)
  const customAnswer = ref('')
  const busy = ref(false)
  const busyMessage = ref('')
  const error = ref('')
  const completedCourse = ref<Course | null>(null)
  const retryAction = shallowRef<RetryAction | null>(null)
  let version = 0

  function applySession(next: IntakeRead) {
    session.value = next
    initialName.value = next.initial_name
    initialIntro.value = next.initial_intro
    if (next.status === 'completed') {
      localStorage.removeItem(ACTIVE_INTAKE_KEY)
      localStorage.removeItem(SKIPPED_INTAKE_KEY)
    } else {
      localStorage.setItem(ACTIVE_INTAKE_KEY, String(next.id))
      localStorage.removeItem(SKIPPED_INTAKE_KEY)
    }
    if (next.brief) phase.value = 'brief'
    else if (next.current_question) phase.value = 'question'
    else if (next.depth_options.length) phase.value = 'depth'
  }

  async function run<T>(
    requestAction: () => Promise<T>,
    onSuccess: (result: T) => void,
    message: string,
  ) {
    if (busy.value) return
    const operationVersion = version
    busy.value = true
    busyMessage.value = message
    error.value = ''
    try {
      const result = await requestAction()
      if (operationVersion !== version) return
      onSuccess(result)
      retryAction.value = null
    } catch (cause) {
      if (operationVersion === version) {
        error.value = errorMessage(cause)
        retryAction.value = () => run(requestAction, onSuccess, message)
      }
    } finally {
      if (operationVersion === version) {
        busy.value = false
        busyMessage.value = ''
      }
    }
  }

  async function start(materialBatchId?: string | null) {
    const name = initialName.value.trim()
    const intro = initialIntro.value.trim()
    if (!name || !intro) return
    await run(
      () => intakeApi.create(name, intro, materialBatchId),
      applySession,
      'AI 正在理解你的学习需求',
    )
  }

  function selectDepth(id: string) {
    if (busy.value) return
    selectedDepthId.value = id
    customDepth.value = false
  }

  function selectCustomDepth() {
    if (busy.value) return
    selectedDepthId.value = null
    customDepth.value = true
  }

  async function submitDepth() {
    if (!session.value) return
    const intakeId = session.value.id
    if (customDepth.value) {
      const count = Math.round(customQuestionCount.value)
      if (count < 1 || count > 20) return
      await run(
        () => intakeApi.selectDepth(intakeId, { question_count: count }),
        applySession,
        'AI 正在准备确认问题',
      )
      return
    }
    if (!selectedDepthId.value) return
    const optionId = selectedDepthId.value
    await run(
      () => intakeApi.selectDepth(intakeId, { option_id: optionId }),
      applySession,
      'AI 正在准备确认问题',
    )
  }

  function selectAnswer(id: string) {
    if (busy.value) return
    selectedOptionId.value = id
    customAnswerSelected.value = false
  }

  function selectCustomAnswer() {
    if (busy.value) return
    selectedOptionId.value = null
    customAnswerSelected.value = true
  }

  async function submitAnswer() {
    const intake = session.value
    const question = intake?.current_question
    if (!intake || !question) return
    const answer = customAnswerSelected.value
      ? { question_id: question.id, custom_answer: customAnswer.value.trim() }
      : selectedOptionId.value
        ? { question_id: question.id, option_id: selectedOptionId.value }
        : null
    if (!answer || ('custom_answer' in answer && !answer.custom_answer)) return
    await run(
      () => intakeApi.answer(intake.id, answer),
      (next) => {
        applySession(next)
        selectedOptionId.value = null
        customAnswerSelected.value = false
        customAnswer.value = ''
      },
      'AI 正在整理你的回答',
    )
  }



  async function confirm() {
    const intake = session.value
    if (!intake?.brief) return
    await run(
      () => intakeApi.confirm(intake.id, intake.brief!),
      (result) => {
        applySession(result.intake)
        completedCourse.value = result.course
      },
      '正在创建课程',
    )
  }

  async function retry() {
    await retryAction.value?.()
  }

  function clearState() {
    version += 1
    phase.value = 'start'
    initialName.value = ''
    initialIntro.value = ''
    session.value = null
    selectedDepthId.value = null
    customDepth.value = false
    customQuestionCount.value = 6
    selectedOptionId.value = null
    customAnswerSelected.value = false
    customAnswer.value = ''
    busy.value = false
    busyMessage.value = ''
    error.value = ''
    completedCourse.value = null
    retryAction.value = null
  }

  function reset() {
    if (session.value) localStorage.setItem(SKIPPED_INTAKE_KEY, String(session.value.id))
    localStorage.removeItem(ACTIVE_INTAKE_KEY)
    clearState()
  }

  async function restore() {
    if (busy.value) return
    const operationVersion = version
    busy.value = true
    busyMessage.value = '正在恢复未完成的需求确认'
    error.value = ''
    try {
      const storedId = Number(localStorage.getItem(ACTIVE_INTAKE_KEY))
      let intake: IntakeRead | null = null
      if (Number.isInteger(storedId) && storedId > 0) {
        try {
          intake = await intakeApi.get(storedId)
        } catch (cause) {
          if (!(cause instanceof HttpError) || cause.status !== 404) throw cause
          localStorage.removeItem(ACTIVE_INTAKE_KEY)
        }
      }
      if (!intake) {
        try {
          intake = await intakeApi.latestActive()
        } catch (cause) {
          if (!(cause instanceof HttpError) || cause.status !== 404) throw cause
        }
      }
      if (operationVersion !== version) return
      const skippedId = Number(localStorage.getItem(SKIPPED_INTAKE_KEY))
      if (intake && intake.id === skippedId) intake = null
      if (intake?.status === 'awaiting_extension') intake = await intakeApi.resume(intake.id)
      if (operationVersion !== version) return
      if (intake && intake.status !== 'completed') applySession(intake)
      else clearState()
      retryAction.value = null
    } catch (cause) {
      if (operationVersion === version) {
        error.value = errorMessage(cause)
        retryAction.value = restore
      }
    } finally {
      if (operationVersion === version) {
        busy.value = false
        busyMessage.value = ''
      }
    }
  }

  return {
    phase,
    initialName,
    initialIntro,
    session,
    selectedDepthId,
    customDepth,
    customQuestionCount,
    selectedOptionId,
    customAnswerSelected,
    customAnswer,
    busy,
    busyMessage,
    error,
    completedCourse,
    start,
    selectDepth,
    selectCustomDepth,
    submitDepth,
    selectAnswer,
    selectCustomAnswer,
    submitAnswer,
    confirm,
    retry,
    reset,
    restore,
  }
}
