import { reactive, ref } from 'vue'
import { errorMessage } from '../../shared/api'
import { coursesApi } from './api'
import {
  courseSummary,
  type Course,
  type CourseInput,
  type CourseSummary,
  type CourseTask,
} from './types'

// 首页保存摘要；完整目录只在进入课程时加载，避免以后一次下载全部讲义。
const courses = ref<CourseSummary[]>([])
const details = reactive<Record<number, Course | undefined>>({})
const loading = ref(true)
const error = ref('')
const detailLoading = reactive<Record<number, boolean | undefined>>({})
const detailErrors = reactive<Record<number, string | undefined>>({})
const tasks = reactive<Record<number, CourseTask | undefined>>({})
const taskErrors = reactive<Record<number, string | undefined>>({})

function put(course: Course) {
  details[course.id] = course
  const summary = courseSummary(course)
  const index = courses.value.findIndex((item) => item.id === course.id)
  if (index < 0) courses.value.unshift(summary)
  else courses.value[index] = summary
}

async function loadCourses() {
  loading.value = true
  error.value = ''
  try {
    courses.value = await coursesApi.list()
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loading.value = false
  }
}

async function loadCourse(id: number, force = false) {
  if ((!force && details[id]) || detailLoading[id]) return
  detailLoading[id] = true
  detailErrors[id] = ''
  try {
    put(await coursesApi.get(id))
  } catch (cause) {
    detailErrors[id] = errorMessage(cause)
  } finally {
    delete detailLoading[id]
  }
}

async function saveCourse(input: CourseInput, id?: number) {
  const course =
    id === undefined ? await coursesApi.create(input) : await coursesApi.update(id, input)
  put(course)
  return course
}

async function generate(courseId: number, chapterId?: number) {
  if (tasks[courseId]) return
  tasks[courseId] = {
    label: chapterId === undefined ? '正在规划课程目录' : '正在生成章节知识点',
    chapterId,
  }
  taskErrors[courseId] = ''
  try {
    const course =
      chapterId === undefined
        ? await coursesApi.outline(courseId)
        : await coursesApi.points(courseId, chapterId, details[courseId]?.outline_version_id ?? null)
    // 用返回结果自己的 ID 更新，绝不依赖此时用户正在看哪门课。
    put(course)
  } catch (cause) {
    taskErrors[courseId] = errorMessage(cause)
  } finally {
    delete tasks[courseId]
  }
}

export function useCourses() {
  return {
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
    rememberCourse: put,
    saveCourse,
    generate,
  }
}
