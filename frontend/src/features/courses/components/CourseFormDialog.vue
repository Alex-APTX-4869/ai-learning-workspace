<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BaseDialog from '../../../shared/components/BaseDialog.vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import { errorMessage } from '../../../shared/api'
import { useCourses } from '../useCourses'
import type { Course } from '../types'

const props = defineProps<{ open: boolean; course?: Course }>()
const emit = defineEmits<{ close: []; saved: [course: Course] }>()
const name = ref(''),
  intro = ref(''),
  error = ref(''),
  saving = ref(false)
const valid = computed(() => !!name.value.trim() && !!intro.value.trim())
const { saveCourse } = useCourses()
watch(
  () => props.open,
  (open) => {
    if (open) {
      name.value = props.course?.name ?? ''
      intro.value = props.course?.intro ?? ''
      error.value = ''
    }
  },
)
async function submit() {
  if (!valid.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const course = await saveCourse(
      { name: name.value.trim(), intro: intro.value.trim() },
      props.course?.id,
    )
    emit('saved', course)
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <BaseDialog :open="open" labelledby="course-form-title" :busy="saving" @close="emit('close')">
    <form class="course-form" @submit.prevent="submit">
      <header class="form-heading">
        <div>
          <p class="eyebrow">一门课程，一次新的探索</p>
          <h2 id="course-form-title">{{ course ? '编辑课程信息' : '创建课程' }}</h2>
        </div>
        <button
          type="button"
          class="icon-button"
          aria-label="关闭课程表单"
          :disabled="saving"
          @click="emit('close')"
        >
          <AppIcon name="close" />
        </button>
      </header>
      <label for="course-name">课程名称</label>
      <input
        id="course-name"
        v-model="name"
        maxlength="200"
        placeholder="例如：从零学习 FastAPI"
        required
        autofocus
        :disabled="saving"
      />
      <label for="course-intro">你希望学会什么？</label>
      <textarea
        id="course-intro"
        v-model="intro"
        rows="5"
        maxlength="12000"
        placeholder="写下你的基础、学习目标，以及希望重点掌握的内容。"
        required
        :disabled="saving"
      />
      <p class="field-hint">
        {{
          course
            ? '修改课程信息不会自动改写已生成的目录和知识点。'
            : '创建后进入课程，让 AI 为你规划章节和小节。'
        }}
      </p>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <footer>
        <button type="button" class="button secondary" :disabled="saving" @click="emit('close')">
          取消</button
        ><button class="button primary" :disabled="!valid || saving">
          <span v-if="saving" class="spinner" />{{
            saving ? '正在保存' : course ? '保存修改' : '创建并进入'
          }}<AppIcon v-if="!saving" name="arrow" />
        </button>
      </footer>
    </form>
  </BaseDialog>
</template>

<style scoped>
.course-form {
  padding: 32px;
}
.form-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 30px;
}
h2 {
  margin-top: 8px;
  font-size: 25px;
}
label {
  display: block;
  font-size: 13px;
  margin: 22px 0 9px;
  font-weight: 550;
}
.field-hint {
  font-size: 12px;
  color: var(--muted);
  margin-top: 10px;
  line-height: 1.8;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 30px;
}
@media (max-width: 480px) {
  .course-form {
    padding: 24px;
  }
}
</style>
