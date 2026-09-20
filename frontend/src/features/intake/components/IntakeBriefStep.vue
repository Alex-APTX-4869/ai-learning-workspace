<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import type { CourseBrief } from '../types'

const props = defineProps<{ brief: CourseBrief; questionCount: number; busy: boolean }>()
const emit = defineEmits<{ confirm: [] }>()
const groups = computed(() => [
  { title: '学习目标', items: props.brief.learning_outcomes },
  { title: '课程范围', items: props.brief.scope_in },
  { title: '暂不包含', items: props.brief.scope_out },
  { title: '学习偏好', items: props.brief.learning_preferences },
  { title: '现实限制', items: props.brief.constraints },
  { title: '完成标准', items: props.brief.success_criteria },
])
</script>

<template>
  <section class="intake-step" aria-labelledby="brief-title">
    <div class="step-copy">
      <p class="eyebrow">需求已经整理完成</p>
      <h2 id="brief-title">确认这份课程需求</h2>
      <p>确认后会创建课程，并以这份需求作为后续章节与小节规划的依据。</p>
    </div>

    <div class="brief-hero">
      <span class="brief-icon"><AppIcon name="book" /></span>
      <div>
        <span class="brief-label">课程名称</span>
        <h3>{{ brief.course_name }}</h3>
        <p>{{ brief.summary || '尚未提供课程摘要' }}</p>
      </div>
    </div>

    <section class="learner-card">
      <span class="brief-label">学习者情况</span>
      <p>{{ brief.learner_profile || '尚未特别说明' }}</p>
    </section>

    <div class="brief-grid">
      <section v-for="group in groups" :key="group.title" class="brief-group">
        <h3>{{ group.title }}</h3>
        <ul v-if="group.items.length">
          <li v-for="item in group.items" :key="item">{{ item }}</li>
        </ul>
        <p v-else class="not-specified">未特别限定</p>
      </section>
    </div>

    <div class="step-actions">
      <button class="button primary" :disabled="busy" @click="emit('confirm')">
        <span v-if="busy" class="spinner" />
        <AppIcon v-else name="check" />
        {{ busy ? '处理中' : '确认并创建课程' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.intake-step {
  max-width: 900px;
  margin: 0 auto;
}
.step-copy {
  margin-bottom: 26px;
}
.step-copy h2 {
  margin: 11px 0 8px;
  font-size: 25px;
}
.step-copy > p:last-child {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.85;
}
.brief-hero {
  display: flex;
  align-items: flex-start;
  gap: 17px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--surface);
}
.brief-icon {
  display: grid;
  place-items: center;
  width: 43px;
  height: 43px;
  flex-shrink: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--soft);
  color: var(--accent);
}
.brief-hero h3 {
  margin: 5px 0 7px;
  font-size: 19px;
  line-height: 1.5;
}
.brief-hero p,
.learner-card p {
  color: var(--body);
  font-size: 13px;
  line-height: 1.85;
}
.brief-label {
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 1px;
}
.learner-card {
  margin-top: 12px;
  padding: 18px 22px;
  border-left: 2px solid #b6c8d5;
  background: var(--soft);
}
.learner-card p {
  margin-top: 6px;
}
.brief-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.brief-group {
  padding: 19px 21px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--surface);
}
.brief-group h3 {
  margin-bottom: 10px;
  font-size: 13px;
}
.brief-group ul {
  margin: 0;
  padding-left: 17px;
  color: var(--body);
  font-size: 12px;
  line-height: 1.8;
}
.brief-group li + li {
  margin-top: 5px;
}
.not-specified {
  color: var(--muted);
  font-size: 12px;
}
.step-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 25px;
}
.question-limit {
  color: var(--muted);
  font-size: 11px;
}
@media (max-width: 640px) {
  .step-copy h2 {
    font-size: 21px;
  }
  .brief-grid {
    grid-template-columns: 1fr;
  }
  .brief-hero {
    padding: 18px;
  }
  .step-actions .button {
    width: 100%;
  }
  .step-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }
}
</style>
