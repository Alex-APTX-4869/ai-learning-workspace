// 无浏览器、无网络、无模型调用的组件渲染和状态回归检查。
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createRenderer, createSSRApp, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'

const vite = await createServer({ server: { middlewareMode: true, watch: null }, appType: 'custom' })
let checks = 0
const mounted = []
async function check(name, action) {
  await action()
  checks++
  console.log(`PASS ${name}`)
}
const module = path => vite.ssrLoadModule(`/src/${path}`)
// Vue 的片段/条件分支会插入水合注释；断言可见标记，不依赖这些内部注释。
const render = async (path, props) => (await renderToString(createSSRApp((await module(path)).default, props))).replace(/<!--[\s\S]*?-->/g, '')
const settle = async () => { await nextTick(); await new Promise(resolve => setImmediate(resolve)); await nextTick() }

try {
  await check('Markdown renders lists, emphasis, code and tables; HTML stays escaped', async () => {
    const html = await render('features/learning/components/SafeMarkdown.vue', {
      source: '**重点** 与 `name`\n\n- 第一项\n- 第二项\n\n| 字段 | 内容 |\n| --- | --- |\n| 名称 | Python |\n\n<script>alert(1)</script>',
    })
    assert.match(html, /<strong[^>]*>重点<\/strong>/)
    assert.match(html, /<code[^>]*>name<\/code>/)
    assert.match(html, /<table/)
    assert.equal((html.match(/<li[\s>]/g) || []).length, 2)
    assert.doesNotMatch(html, /<script>/)
    assert.match(html, /&lt;script&gt;/)
  })
  await check('Learning goals display separate items and collapse long text', async () => {
    const html = await render('features/learning/components/LearningGoals.vue', {
      intro: '这是一个独立的学习目标。'.repeat(30),
    })
    assert.match(html, /collapsed/)
    assert.match(html, /展开全部目标/)
    assert.equal((html.match(/<li[\s>]/g) || []).length, 30)
  })
  await check('Inline code inside emphasis renders without exposing HTML or formatting code contents', async () => {
    const html = await render('features/learning/components/SafeMarkdown.vue', {
      source: '**识别 `/items/abc` 中的 `422`**\n\n*检查 `<img onerror=alert(1)>`*\n\n`**保持原样**`',
    })
    assert.match(html, /<strong[^>]*>[\s\S]*<code[^>]*>\/items\/abc<\/code>/)
    assert.match(html, /<code[^>]*>422<\/code>/)
    assert.doesNotMatch(html, /`\/items\/abc`/)
    assert.doesNotMatch(html, /<img/)
    assert.match(html, /&lt;img onerror=alert\(1\)&gt;/)
    assert.match(html, /<code[^>]*>\*\*保持原样\*\*<\/code>/)
  })
  await check('Structured goals replace the original long introduction', async () => {
    const html = await render('features/learning/components/LearningGoals.vue', {
      intro: '不应显示的旧简介', goals: ['解释键和值。', '按键读取名称。'],
    })
    assert.match(html, /解释键和值/)
    assert.doesNotMatch(html, /不应显示的旧简介/)
  })
  const exercise = { kind: 'single_choice', question: '哪项是键？', options: [{ label: 'A', text: 'name' }, { label: 'B', text: 'Python' }], hint: '想想字段名。' }
  await check('Exercise renders choices without showing unsubmitted answers', async () => {
    const html = await render('features/tutor/components/TutorExercise.vue', { exercise, response: null, disabled: false })
    assert.equal((html.match(/type="radio"/g) || []).length, 2)
    assert.match(html, /提交答案/)
    assert.doesNotMatch(html, /回答正确/)
    assert.doesNotMatch(html, /参考答案是/)
  })
  await check('Exercise displays persisted feedback without claiming mastery', async () => {
    const html = await render('features/tutor/components/TutorExercise.vue', {
      exercise, disabled: false, response: { selected: [0], written_answer: '', correct: true, answer: '参考答案是 A', explanation: '键表示字段名。' },
    })
    assert.match(html, /回答正确/)
    assert.match(html, /参考答案是 A/)
    assert.match(html, /checked/)
    assert.doesNotMatch(html, /已经掌握/)
  })
  await check('Judgment and solution questions have independent answer controls', async () => {
    for (const path of ['features/tutor/components/TutorExercise.vue', 'features/learning/components/ExerciseCard.vue']) {
      const judgment = await render(path, { number: 1, disabled: false, response: null,
        exercise: { kind: 'true_false', question: '字典通过键读取值。', options: [
          { label: 'A', text: '正确', correct: true }, { label: 'B', text: '错误', correct: false },
        ], answer: '正确', explanation: '键标识对应的值。' } })
      assert.match(judgment, /判断题/)
      assert.equal((judgment.match(/type="radio"/g) || []).length, 2)
      assert.doesNotMatch(judgment, />A(?:\.|<)/)
      const solution = await render(path, { number: 2, disabled: false, response: null,
        exercise: { kind: 'short_answer', question: '解释键和值的关系。', options: [], answer: '参考思路', explanation: '解析' } })
      assert.match(solution, /解答题/)
      assert.match(solution, /<textarea/)
      assert.doesNotMatch(solution, /type="radio"/)
    }
  })

  const { useTutorSession } = await module('features/tutor/useTutorSession.ts')
  const { tutorApi } = await module('features/tutor/api.ts')
  const { HttpError } = await module('shared/api.ts')
  const state = (overrides = {}) => ({ id: 1, course_id: 1, outline_version_id: 1, point_id: 1, content_version_id: 1, revision: 0,
    card_index: 0, card_count: 2, completed: false, busy: false,
    current_card: { id: 'lesson-0', kind: 'lesson', title: '卡片', body_markdown: '内容' }, stages: [], response: null, turns: [], ...overrides })
  // 内存宿主只用于驱动 Vue 生命周期；不控制或访问真实浏览器。
  const renderer = createRenderer({
    createElement: () => ({}), createText: text => ({ text }), createComment: text => ({ text }),
    insert() {}, remove() {}, setText() {}, setElementText() {}, patchProp() {}, parentNode: () => null, nextSibling: () => null,
  })
  function mount() {
    let result
    const app = renderer.createApp({ setup() { result = useTutorSession(ref(1), ref(1), ref(1), ref(1)); return () => null } })
    app.mount({})
    mounted.push(app)
    return { app, result }
  }
  await check('Uncertain network result reuses the exact request ID and blocks duplicate actions', async () => {
    tutorApi.start = async () => state()
    const payloads = []
    tutorApi.action = async (_, payload) => {
      payloads.push(structuredClone(payload))
      if (payloads.length === 1) throw new Error('连接中断')
      return state({ revision: 1, card_index: 1, current_card: { id: 'lesson-1', kind: 'lesson', title: '下一张' } })
    }
    const { app, result } = mount()
    await settle()
    assert.equal(await result.act('next'), false)
    assert.equal(result.retryable.value, true)
    assert.equal(await result.act('next'), false)
    await result.retry()
    assert.deepEqual(payloads[0], payloads[1])
    assert.equal(result.session.value.card_index, 1)
    assert.equal(result.retryable.value, false)
    app.unmount()
  })
  await check('A stale action synchronizes to server progress instead of retrying the old action', async () => {
    tutorApi.start = async () => state()
    tutorApi.action = async () => { throw new HttpError('进度已变化', 409) }
    tutorApi.session = async () => state({ revision: 3, card_index: 1 })
    const { app, result } = mount()
    await settle()
    await result.act('next')
    assert.equal(result.session.value.revision, 3)
    assert.equal(result.retryable.value, false)
    app.unmount()
  })
  await check('Leaving aborts local polling, never sends a cancel operation, and reopening resumes', async () => {
    let signal
    let actionCalls = 0
    tutorApi.start = async (_, __, ___, ____, currentSignal) => { signal = currentSignal; return state({ busy: true, card_index: 1 }) }
    tutorApi.action = async () => { actionCalls++; return state() }
    const first = mount()
    await settle()
    first.app.unmount()
    assert.equal(signal.aborted, true)
    assert.equal(actionCalls, 0)
    tutorApi.start = async () => state({ busy: false, card_index: 1, revision: 2 })
    const second = mount()
    await settle()
    assert.equal(second.result.session.value.card_index, 1)
    second.app.unmount()
  })
  await check('Responses arriving after leaving cannot replace local state', async () => {
    let finish
    tutorApi.start = () => new Promise(resolve => { finish = resolve })
    const { app, result } = mount()
    app.unmount()
    finish(state())
    await settle()
    assert.equal(result.session.value, null)
  })
  await check('A content version mismatch is surfaced rather than silently resuming wrong cards', async () => {
    tutorApi.start = async () => state({ content_version_id: 2 })
    const { app, result } = mount()
    await settle()
    assert.equal(result.session.value, null)
    assert.match(result.error.value, /版本已更新/)
    app.unmount()
  })
  console.log(`${checks} learning frontend checks passed`)
} finally {
  for (const app of mounted) app.unmount()
  await vite.close()
}
