import { onBeforeUnmount, ref } from 'vue'
import type { CodeLab } from './types'

type TestResult = { name: string; passed: boolean; error: string | null }
type WorkerMessage = {
  type: 'loading' | 'running' | 'result' | 'error'
  token: string
  result?: { student_error: string | null; tests: TestResult[] }
  output?: string
  truncated?: boolean
  error?: string
}

const LOAD_TIMEOUT_MS = 60_000
const EXECUTION_TIMEOUT_MS = 8_000

export function usePythonLab() {
  const running = ref(false)
  const phase = ref<'idle' | 'loading' | 'running'>('idle')
  const output = ref('')
  const truncated = ref(false)
  const error = ref('')
  const studentError = ref<string | null>(null)
  const testResults = ref<TestResult[]>([])
  let worker: Worker | null = null
  let timer: number | null = null
  let token = ''

  function clearTimer() {
    if (timer !== null) window.clearTimeout(timer)
    timer = null
  }

  function disposeWorker() {
    clearTimer()
    worker?.terminate()
    worker = null
    running.value = false
    phase.value = 'idle'
  }

  function setTimeoutGuard(milliseconds: number, message: string) {
    clearTimer()
    timer = window.setTimeout(() => {
      disposeWorker()
      error.value = message
    }, milliseconds)
  }

  function run(code: string, lab: CodeLab) {
    if (running.value || !code.trim()) return
    disposeWorker()
    output.value = ''
    truncated.value = false
    error.value = ''
    studentError.value = null
    testResults.value = []
    running.value = true
    phase.value = 'loading'
    token = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    worker = new Worker(new URL('./pythonLabWorker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
      const message = event.data
      if (message.token !== token) return
      if (message.type === 'loading') {
        phase.value = 'loading'
        return
      }
      if (message.type === 'running') {
        phase.value = 'running'
        setTimeoutGuard(EXECUTION_TIMEOUT_MS, '运行超过 8 秒，已终止代码。')
        return
      }
      if (message.type === 'error') {
        error.value = message.error || '代码运行失败。'
        disposeWorker()
        return
      }
      output.value = message.output || ''
      truncated.value = !!message.truncated
      studentError.value = message.result?.student_error || null
      testResults.value = message.result?.tests || []
      disposeWorker()
    }
    worker.onerror = () => {
      error.value = '无法启动 Python 运行环境，请检查网络后重试。'
      disposeWorker()
    }
    setTimeoutGuard(LOAD_TIMEOUT_MS, 'Python 运行环境加载超时，请检查网络后重试。')
    worker.postMessage({ token, code, tests: lab.tests })
  }

  function stop() {
    if (!running.value) return
    disposeWorker()
    error.value = '已停止本次代码运行。'
  }

  function reset() {
    disposeWorker()
    output.value = ''
    truncated.value = false
    error.value = ''
    studentError.value = null
    testResults.value = []
  }

  onBeforeUnmount(disposeWorker)

  return {
    running,
    phase,
    output,
    truncated,
    error,
    studentError,
    testResults,
    run,
    stop,
    reset,
  }
}
