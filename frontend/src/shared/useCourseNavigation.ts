import { onBeforeUnmount, onMounted, ref } from 'vue'

function readCourseId(): number | null {
  const match = window.location.hash.match(/^#\/courses\/(\d+)$/)
  return match ? Number(match[1]) : null
}

export function useCourseNavigation() {
  const courseId = ref(readCourseId())
  const sync = () => {
    courseId.value = readCourseId()
  }
  onMounted(() => window.addEventListener('hashchange', sync))
  onBeforeUnmount(() => window.removeEventListener('hashchange', sync))
  // Hash 路由使课程链接可刷新、可分享，并支持浏览器前进/后退。
  function navigate(id: number | null) {
    window.location.hash = id === null ? '/' : `/courses/${id}`
  }
  return { courseId, navigate }
}
