<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import CourseLibrary from './pages/CourseLibrary.vue'
import CourseWorkspace from './pages/CourseWorkspace.vue'
import CourseFormDialog from './features/courses/components/CourseFormDialog.vue'
import AppIcon from './shared/components/AppIcon.vue'
import { useCourses } from './features/courses/useCourses'
import { useCourseNavigation } from './shared/useCourseNavigation'
import type { Course } from './features/courses/types'

const {
  courses,
  details,
  loading,
  error,
  detailLoading,
  detailErrors,
  tasks,
  taskErrors,
  loadCourses,
  loadCourse,
  generate,
} = useCourses()
const { courseId, navigate } = useCourseNavigation()
const course = computed(() => (courseId.value === null ? undefined : details[courseId.value]))
const courseTitle = computed(
  () =>
    course.value?.name || courses.value.find((item) => item.id === courseId.value)?.name || '课程',
)
const formOpen = ref(false)
const editingCourse = ref<Course>()
onMounted(() => {
  loadCourses()
  if (courseId.value !== null) loadCourse(courseId.value)
})
watch(courseId, (id) => {
  if (id !== null) loadCourse(id)
})
function openForm(edit?: Course) {
  editingCourse.value = edit
  formOpen.value = true
}
function saved(item: Course) {
  formOpen.value = false
  navigate(item.id)
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="#/" aria-label="学习空间首页"
        ><span class="brand-mark"><AppIcon name="book" /></span
        ><span>学习空间<small>让好奇有迹可循</small></span></a
      >
      <p class="sidebar-caption">我的工作台</p>
      <a href="#/" class="sidebar-link" :aria-current="courseId === null ? 'page' : undefined"
        ><AppIcon name="grid" />我的课程<AppIcon name="chevron"
      /></a>
      <div class="sidebar-bottom">
        <span class="personal-avatar">我</span
        ><span>个人学习空间<small>按自己的节奏生长</small></span>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <nav class="breadcrumbs" aria-label="当前位置">
          <a href="#/">我的课程</a
          ><template v-if="courseId !== null"
            ><AppIcon name="chevron" /><span>{{ courseTitle }}</span></template
          >
        </nav>
        <span class="workspace-badge"><span />个人工作台</span>
      </header>
      <main id="main-content">
        <CourseLibrary
          v-if="courseId === null"
          :courses="courses"
          :loading="loading"
          :error="error"
          :tasks="tasks"
          @create="openForm()"
          @retry="loadCourses"
        />
        <div v-else-if="detailLoading[courseId]" class="loading-state" role="status">
          <span class="spinner" />正在打开课程…
        </div>
        <CourseWorkspace
          v-else-if="course"
          :key="course.id"
          :course="course"
          :task="tasks[course.id]"
          :error="taskErrors[course.id]"
          @edit="openForm(course)"
          @generate="generate(course!.id, $event)"
        />
        <section v-else class="empty-state page-content">
          <h1>{{ detailErrors[courseId] ? '课程暂时无法加载' : '没有找到这门课程' }}</h1>
          <p>{{ detailErrors[courseId] || '课程可能已移除，请回到列表查看。' }}</p>
          <button
            v-if="detailErrors[courseId]"
            class="button secondary"
            @click="loadCourse(courseId, true)"
          >
            重试</button
          ><button class="button primary" @click="navigate(null)">返回我的课程</button>
        </section>
      </main>
    </div>
    <CourseFormDialog
      :open="formOpen"
      :course="editingCourse"
      @close="formOpen = false"
      @saved="saved"
    />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100dvh;
}
.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: 218px;
  background: #f7f9fbcc;
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 35px 19px 24px;
  z-index: 2;
}
.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  text-decoration: none;
  color: var(--ink);
  font-size: 18px;
  font-weight: 550;
  padding: 0 9px;
}
.brand-mark {
  width: 36px;
  height: 40px;
  display: grid;
  place-items: center;
  background: #fff;
  border: 1px solid #dce4eb;
  border-radius: 9px;
  color: var(--accent);
  box-shadow: 0 2px 4px #172f4503;
}
.brand small {
  display: block;
  font-size: 10px;
  font-weight: 400;
  color: var(--muted);
  margin-top: 5px;
  letter-spacing: 1px;
}
.sidebar-caption {
  font-size: 10px;
  color: #788795;
  margin: 57px 12px 14px;
  letter-spacing: 1px;
}
.sidebar-link {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 13px;
  border-radius: 8px;
  color: #486579;
  background: #e9eff4;
  font-size: 13px;
  text-decoration: none;
}
.sidebar-link > .app-icon {
  width: 17px;
  height: 17px;
}
.sidebar-link > .app-icon:last-child {
  margin-left: auto;
  width: 12px;
}
.sidebar-bottom {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--line);
  padding: 23px 9px 0;
  font-size: 12px;
}
.personal-avatar {
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  background: #edf1f5;
  border: 1px solid var(--line);
  border-radius: 50%;
  color: #71869a;
  font-size: 11px;
}
.sidebar-bottom small {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 5px;
}
.main-shell {
  margin-left: 218px;
}
.topbar {
  height: 75px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  border-bottom: 1px solid var(--line);
  padding: 0 48px;
  background: #ffffff8c;
}
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  min-width: 0;
}
.breadcrumbs a {
  color: var(--muted);
  text-decoration: none;
  white-space: nowrap;
}
.breadcrumbs a:hover {
  color: var(--ink);
}
.breadcrumbs .app-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: #a7b3bf;
}
.breadcrumbs > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workspace-badge {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}
.workspace-badge > span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #8fa9bb;
}
@media (min-width: 1600px) {
  .topbar {
    padding: 0 max(48px, calc((100vw - 218px - 1140px) / 2));
  }
}
@media (max-width: 1000px) {
  .sidebar {
    width: 190px;
    padding-inline: 14px;
  }
  .main-shell {
    margin-left: 190px;
  }
  .topbar {
    padding: 0 30px;
  }
}
@media (max-width: 760px) {
  .sidebar {
    position: static;
    width: 100%;
    height: 68px;
    padding: 14px 22px;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .brand {
    padding: 0;
    font-size: 16px;
  }
  .brand small,
  .sidebar-caption,
  .sidebar-bottom {
    display: none;
  }
  .brand-mark {
    width: 30px;
    height: 33px;
  }
  .sidebar-link {
    padding: 9px 12px;
    font-size: 12px;
  }
  .sidebar-link > .app-icon:last-child {
    display: none;
  }
  .main-shell {
    margin-left: 0;
  }
  .topbar {
    height: 53px;
    padding: 0 24px;
  }
  .workspace-badge {
    display: none;
  }
}
</style>
