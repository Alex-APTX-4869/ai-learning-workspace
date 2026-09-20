<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CodeLab } from '../types'
import { usePythonLab } from '../usePythonLab'
import SafeMarkdown from './SafeMarkdown.vue'

const props = defineProps<{ lab: CodeLab }>()
const code = ref(props.lab.starter_code)
const {
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
} = usePythonLab()
const allPassed = computed(
  () => testResults.value.length > 0 && testResults.value.every((test) => test.passed),
)

watch(
  () => props.lab,
  (lab) => {
    reset()
    code.value = lab.starter_code
  },
)

function toggleRun() {
  if (running.value) stop()
  else run(code.value, props.lab)
}
</script>

<template>
  <section class="code-lab">
    <header>
      <div>
        <span class="item-number">Python 代码实验</span>
        <h3>{{ lab.title }}</h3>
      </div>
      <span class="runtime-tag">浏览器内运行</span>
    </header>
    <SafeMarkdown :source="lab.instructions_markdown" />
    <p class="runtime-note">
      代码在独立 Web Worker 中通过 Pyodide 执行，不会在 FastAPI 服务器上运行。首次需下载 Python 运行环境。
    </p>

    <div class="editor-heading">
      <span>你的代码</span>
      <button type="button" class="text-button" :disabled="running" @click="code = lab.starter_code">
        重置
      </button>
    </div>
    <textarea
      v-model="code"
      class="code-editor"
      spellcheck="false"
      aria-label="Python 代码编辑器"
    />
    <div class="lab-actions">
      <button type="button" class="button primary" @click="toggleRun">
        {{
          running
            ? '停止运行'
            : phase === 'loading'
              ? '正在加载'
              : '运行并检查'
        }}
      </button>
      <span v-if="running" role="status">
        {{ phase === 'loading' ? '正在加载 Python…' : '正在运行，超过 8 秒会自动终止…' }}
      </span>
    </div>

    <div v-if="error" class="lab-error" role="alert">{{ error }}</div>
    <section v-if="output || studentError || testResults.length" class="run-result" aria-live="polite">
      <h4>运行结果</h4>
      <pre v-if="output"><code>{{ output }}</code></pre>
      <p v-if="truncated" class="output-warning">输出过长，已截断。</p>
      <p v-if="studentError" class="student-error">{{ studentError }}</p>
      <div v-if="testResults.length" class="test-results">
        <strong :class="{ passed: allPassed }">
          {{ allPassed ? '全部检查通过' : '还有检查未通过' }}
        </strong>
        <ul>
          <li v-for="test in testResults" :key="test.name" :class="{ passed: test.passed }">
            <span>{{ test.passed ? '✓' : '×' }}</span>{{ test.name }}
            <small v-if="test.error">{{ test.error }}</small>
          </li>
        </ul>
      </div>
    </section>

    <details class="solution">
      <summary>查看参考实现</summary>
      <pre><code>{{ lab.solution_code }}</code></pre>
    </details>
  </section>
</template>

<style scoped>
.code-lab {
  padding: 21px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #fff;
}
.code-lab > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 13px;
}
.item-number {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.5px;
}
h3 {
  margin-top: 5px;
  font-size: 18px;
}
.runtime-tag {
  padding: 4px 7px;
  border: 1px solid #d5e2ea;
  border-radius: 5px;
  color: var(--accent);
  background: var(--soft);
  font-size: 10px;
}
.runtime-note {
  margin-top: 15px;
  padding: 10px 12px;
  border-left: 2px solid #b3c7d6;
  color: var(--muted);
  background: var(--soft);
  font-size: 10px;
  line-height: 1.7;
}
.editor-heading {
  display: flex;
  justify-content: space-between;
  margin: 19px 0 7px;
  color: var(--body);
  font-size: 11px;
}
.text-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
}
.code-editor {
  width: 100%;
  min-height: 250px;
  resize: vertical;
  border: 1px solid #dce5ec;
  border-radius: 9px;
  padding: 15px;
  color: #263746;
  background: #f4f7f9;
  font: 13px/1.75 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  tab-size: 4;
}
.lab-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.lab-actions span {
  color: var(--muted);
  font-size: 10px;
}
.lab-error,
.run-result {
  margin-top: 14px;
  border-radius: 9px;
  padding: 13px 14px;
  font-size: 11px;
}
.lab-error {
  border: 1px solid #f0d9d7;
  color: var(--danger);
  background: #fdf4f3;
}
.run-result {
  border: 1px solid var(--line);
  background: var(--soft);
}
.run-result h4 {
  margin-bottom: 9px;
  font-size: 12px;
}
.run-result pre,
.solution pre {
  overflow-x: auto;
  padding: 12px;
  border-radius: 7px;
  color: #31404d;
  background: #edf2f5;
  font: 11px/1.7 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
}
.student-error,
.output-warning {
  margin-top: 8px;
  color: var(--danger);
}
.test-results {
  margin-top: 12px;
}
.test-results > strong {
  color: #87654e;
}
.test-results > strong.passed,
.test-results li.passed {
  color: var(--accent);
}
.test-results ul {
  display: grid;
  gap: 6px;
  margin-top: 8px;
  padding: 0;
  list-style: none;
}
.test-results li span {
  display: inline-block;
  width: 18px;
}
.test-results small {
  display: block;
  margin: 2px 0 0 18px;
  color: var(--muted);
}
.solution {
  margin-top: 15px;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
.solution summary {
  cursor: pointer;
  color: var(--accent);
  font-size: 11px;
}
.solution pre {
  margin-top: 10px;
}
@media (max-width: 640px) {
  .code-lab {
    padding: 16px;
  }
  .lab-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
