<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ goals?: string[]; intro: string }>()
const expanded = ref(false)
const items = computed(() => props.goals?.length ? props.goals : props.intro
  .split(/\n+|(?<=[。！？])\s*/u).map(item => item.replace(/^\s*[-•*]\s*/, '').trim()).filter(Boolean))
const long = computed(() => items.value.join('').length > 220 || items.value.length > 3)
watch(() => props.intro, () => { expanded.value = false })
</script>

<template>
  <section class="learning-goals" aria-label="你将学到">
    <span>你将学到</span>
    <ul :class="{ collapsed: long && !expanded }"><li v-for="(item, index) in items" :key="index">{{ item }}</li></ul>
    <button v-if="long" type="button" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? '收起目标' : '展开全部目标' }}
    </button>
  </section>
</template>

<style scoped>
.learning-goals { padding-left: 17px; border-left: 2px solid #b3c7d6; }
.learning-goals > span { color: var(--accent); font-size: 11px; }
ul { padding-left: 17px; margin: 8px 0 0; color: var(--body); font-size: 13px; line-height: 1.8; }
li + li { margin-top: 5px; }
ul.collapsed { max-height: 100px; overflow: hidden; mask-image: linear-gradient(#000 72%, transparent); }
button { margin-top: 8px; padding: 0; border: 0; background: transparent; color: var(--accent); font-size: 11px; }
</style>
