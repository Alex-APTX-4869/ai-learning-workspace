<script setup lang="ts">
import { ref, watch } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { Point } from '../../courses/types'
const props = defineProps<{ point: Point }>()
const mode = ref('lesson')
watch(
  () => props.point.id,
  () => {
    mode.value = 'lesson'
  },
)
</script>

<template>
  <article class="point-content">
    <p class="eyebrow">专注此刻，理解一个知识点</p>
    <h2>{{ point.name }}</h2>
    <nav class="content-tabs" aria-label="知识点内容类型">
      <button :aria-pressed="mode === 'lesson'" @click="mode = 'lesson'">讲解</button
      ><button :aria-pressed="mode === 'practice'" @click="mode = 'practice'">练习</button
      ><button :aria-pressed="mode === 'code'" @click="mode = 'code'">代码实验</button>
    </nav>
    <div v-if="mode === 'lesson'">
      <section class="learning-objective">
        <span class="tiny-heading">你将学到</span>
        <p>{{ point.intro }}</p>
      </section>
      <!-- 当前只显示真实保存的内容。Markdown 富文本渲染在内容制作阶段接入。 -->
      <section v-if="point.content_markdown" class="saved-content">
        <h3>已保存的内容</h3>
        <pre>{{ point.content_markdown }}</pre>
      </section>
      <section v-else class="content-pending">
        <AppIcon name="book" />
        <h3>为深入学习留一点空间</h3>
        <p>知识点简介已就绪。详细讲解与示例将在内容制作功能接入后提供。</p>
        <span class="plain-tag">详细讲解 · 待接入</span>
      </section>
    </div>
    <section v-else-if="mode === 'practice'" class="content-pending">
      <AppIcon name="edit" />
      <h3>理解之后，动手检验</h3>
      <p>练习与答案解析尚未接入。后续将围绕本知识点的讲解生成对应题目。</p>
      <span class="plain-tag">练习制作 · 待接入</span>
    </section>
    <section v-else class="content-pending">
      <AppIcon name="code" />
      <h3>让知识在代码里发生</h3>
      <p>Python 运行环境尚未接入。后续可以在这里编写代码、查看结果并获得讲解。</p>
      <span class="plain-tag">Python 实验 · 待接入</span>
    </section>
  </article>
</template>

<style scoped>
.point-content {
  padding: 36px 44px;
  max-width: 800px;
  margin: 0 auto;
}
h2 {
  font-size: 27px;
  margin: 12px 0 24px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.content-tabs {
  display: flex;
  gap: 26px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 28px;
}
.content-tabs button {
  padding: 0 0 13px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
}
.content-tabs button[aria-pressed='true'] {
  color: var(--ink);
  border-bottom-color: var(--accent);
}
.learning-objective {
  border-left: 2px solid #b3c7d6;
  padding: 3px 0 3px 18px;
}
.tiny-heading {
  font-size: 12px;
  color: var(--accent);
}
.learning-objective p {
  margin-top: 9px;
  line-height: 1.95;
  font-size: 14px;
  color: var(--body);
}
.content-pending {
  text-align: center;
  padding: 58px 12px 30px;
  color: var(--muted);
}
.content-pending > .app-icon {
  width: 28px;
  height: 28px;
  color: #98aabc;
}
h3 {
  font-size: 17px;
  color: var(--ink);
  margin: 18px 0 10px;
}
.content-pending p {
  max-width: 360px;
  margin: 0 auto 20px;
  font-size: 13px;
  line-height: 1.9;
}
.saved-content pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  line-height: 1.8;
  font-size: 14px;
}
@media (max-width: 640px) {
  .point-content {
    padding: 24px;
  }
  h2 {
    font-size: 22px;
  }
  .content-pending {
    padding-top: 32px;
  }
}
</style>
