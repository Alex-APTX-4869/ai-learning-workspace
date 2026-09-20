<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import { useCourseBrief } from '../useCourseBrief'
import type { Course } from '../types'

const props = defineProps<{ course: Course }>()
const { brief, loading, loaded, error, load } = useCourseBrief(
  props.course.id,
  props.course.outline_version_id,
)
const groups = computed(() =>
  brief.value
    ? [
        { title: '学习目标', items: brief.value.learning_outcomes },
        { title: '课程范围', items: brief.value.scope_in },
        { title: '暂不包含', items: brief.value.scope_out },
        { title: '学习偏好', items: brief.value.learning_preferences },
        { title: '现实限制', items: brief.value.constraints },
        { title: '完成标准', items: brief.value.success_criteria },
      ]
    : [],
)

onMounted(load)
</script>

<template>
  <section class="course-info" aria-labelledby="course-info-title">
    <header class="info-heading">
      <div>
        <p class="eyebrow">课程设计依据</p>
        <h2 id="course-info-title">课程信息</h2>
      </div>
      <span v-if="brief" class="confirmed-tag"><AppIcon name="check" />需求已确认</span>
    </header>

    <div v-if="!loaded && !error" class="info-state" role="status">
      <span class="spinner" />正在读取课程需求…
    </div>
    <div v-else-if="error" class="info-error" role="alert">
      <div>
        <strong>课程需求暂时无法读取</strong>
        <p>{{ error }}</p>
      </div>
      <button type="button" class="button secondary small" :disabled="loading" @click="load">
        重试
      </button>
    </div>

    <template v-else-if="brief">
      <section class="summary-card">
        <span>课程名称</span>
        <h3>{{ brief.course_name }}</h3>
        <p>{{ brief.summary || '尚未提供课程摘要' }}</p>
      </section>
      <section class="learner-card">
        <span>学习者情况</span>
        <p>{{ brief.learner_profile || '尚未特别说明' }}</p>
      </section>
      <div class="brief-grid">
        <section v-for="group in groups" :key="group.title" class="brief-group">
          <h3>{{ group.title }}</h3>
          <ul v-if="group.items.length">
            <li v-for="item in group.items" :key="item">{{ item }}</li>
          </ul>
          <p v-else>未特别限定</p>
        </section>
      </div>
    </template>

    <section v-else class="legacy-info">
      <span class="unconfirmed-tag">未经过需求确认</span>
      <h3>{{ course.name }}</h3>
      <p>{{ course.intro }}</p>
      <small>这门课程只保存了名称和简介，因此这里不会补造学习目标或限制条件。</small>
    </section>
  </section>
</template>

<style scoped>
.course-info {
  max-width: 920px;
  margin: 0 auto;
}
.info-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 17px;
}
.info-heading h2 {
  margin-top: 6px;
  font-size: 20px;
}
.confirmed-tag,
.unconfirmed-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
  font-size: 10px;
}
.confirmed-tag .app-icon {
  width: 14px;
}
.info-state {
  display: flex;
  min-height: 190px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: var(--muted);
  font-size: 12px;
}
.info-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border: 1px solid #f0d9d7;
  border-radius: 10px;
  background: #fdf4f3;
  color: var(--danger);
}
.info-error strong {
  font-size: 12px;
}
.info-error p {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.7;
}
.summary-card,
.learner-card,
.brief-group,
.legacy-info {
  border: 1px solid var(--line);
  background: #fff;
}
.summary-card {
  padding: 21px 22px;
  border-radius: 13px;
}
.summary-card > span,
.learner-card > span {
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.6px;
}
.summary-card h3 {
  margin: 6px 0 8px;
  font-size: 18px;
}
.summary-card p,
.learner-card p,
.legacy-info p {
  color: var(--body);
  font-size: 13px;
  line-height: 1.9;
  white-space: pre-line;
}
.learner-card {
  margin-top: 10px;
  padding: 17px 22px;
  border-radius: 10px;
  background: var(--soft);
}
.learner-card p {
  margin-top: 6px;
}
.brief-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.brief-group {
  padding: 18px 20px;
  border-radius: 10px;
}
.brief-group h3 {
  margin-bottom: 9px;
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
  margin-top: 4px;
}
.brief-group > p {
  color: var(--muted);
  font-size: 11px;
}
.legacy-info {
  padding: 23px;
  border-radius: 13px;
}
.unconfirmed-tag {
  padding: 4px 7px;
  border: 1px solid #e1e6ea;
  border-radius: 5px;
  color: var(--muted);
  background: var(--soft);
}
.legacy-info h3 {
  margin: 13px 0 8px;
  font-size: 18px;
}
.legacy-info small {
  display: block;
  margin-top: 16px;
  padding-top: 13px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
}
@media (max-width: 640px) {
  .brief-grid {
    grid-template-columns: 1fr;
  }
  .info-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .info-error {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
