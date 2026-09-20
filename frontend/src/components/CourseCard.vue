<script setup lang="ts">

// 当前组件只展示父组件传来的课程，暂不需要响应式变量或挂载逻辑；用到时再启用。
// import { ref, onMounted } from 'vue'

type Course= {
  id: number
  name: string
  intro: string
}

defineProps<{
    course: Course
}>()

</script>

<template>
    <div>
        <h2>{{course.name}}</h2>
        <p>{{course.intro}}</p>
    </div>
</template>
