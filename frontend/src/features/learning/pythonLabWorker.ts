const PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/v314.0.6/full/'
const MAX_OUTPUT_LENGTH = 12_000

type LabTest = { name: string; assertion_code: string }
type RunRequest = {
  token: string
  code: string
  tests: LabTest[]
}
type PyodideApi = {
  globals: {
    set: (name: string, value: unknown) => void
    delete: (name: string) => void
  }
  runPythonAsync: (code: string) => Promise<unknown>
  setStdout: (options: { batched: (text: string) => void }) => void
  setStderr: (options: { batched: (text: string) => void }) => void
}
type PyodideModule = {
  loadPyodide: (options: { indexURL: string }) => Promise<PyodideApi>
}

let runtimePromise: Promise<PyodideApi> | null = null

async function runtime() {
  if (!runtimePromise) {
    const moduleUrl = `${PYODIDE_BASE}pyodide.mjs`
    runtimePromise = import(/* @vite-ignore */ moduleUrl).then((module) =>
      (module as PyodideModule).loadPyodide({ indexURL: PYODIDE_BASE }),
    )
  }
  return runtimePromise
}

self.onmessage = async (event: MessageEvent<RunRequest>) => {
  const { token, code, tests } = event.data
  self.postMessage({ type: 'loading', token })
  try {
    const pyodide = await runtime()
    self.postMessage({ type: 'running', token })

    let output = ''
    let truncated = false
    const appendOutput = (text: string) => {
      if (output.length >= MAX_OUTPUT_LENGTH) {
        truncated = true
        return
      }
      const remaining = MAX_OUTPUT_LENGTH - output.length
      output += `${text}\n`.slice(0, remaining)
      if (text.length + 1 > remaining) truncated = true
    }
    pyodide.setStdout({ batched: appendOutput })
    pyodide.setStderr({ batched: appendOutput })
    pyodide.globals.set('__student_source', code)
    pyodide.globals.set('__lab_tests_json', JSON.stringify(tests))

    const serialized = await pyodide.runPythonAsync(`
import json

_lab_namespace = {}
_lab_response = {"student_error": None, "tests": []}
try:
    exec(__student_source, _lab_namespace)
except BaseException as _student_error:
    _lab_response["student_error"] = f"{type(_student_error).__name__}: {_student_error}"

if _lab_response["student_error"] is None:
    for _test in json.loads(__lab_tests_json):
        try:
            exec(_test["assertion_code"], _lab_namespace)
            _lab_response["tests"].append({"name": _test["name"], "passed": True, "error": None})
        except BaseException as _test_error:
            _lab_response["tests"].append({
                "name": _test["name"],
                "passed": False,
                "error": f"{type(_test_error).__name__}: {_test_error}",
            })

json.dumps(_lab_response, ensure_ascii=False)
`)
    pyodide.globals.delete('__student_source')
    pyodide.globals.delete('__lab_tests_json')
    self.postMessage({
      type: 'result',
      token,
      result: JSON.parse(String(serialized)),
      output,
      truncated,
    })
  } catch (error) {
    self.postMessage({
      type: 'error',
      token,
      error: error instanceof Error ? error.message : '代码运行环境加载失败。',
    })
  }
}

export {}
