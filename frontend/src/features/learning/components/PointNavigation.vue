<script setup lang="ts">
import type { Point } from '../../courses/types'
defineProps<{ points: Point[]; selectedId: number | null }>()
defineEmits<{ select: [id: number] }>()
</script>

<template>
  <nav class="point-navigation" aria-label="本小节知识点">
    <p class="eyebrow">
      本节知识点 <span>{{ points.length }}</span>
    </p>
    <ol>
      <li v-for="(point, index) in points" :key="point.id">
        <button :aria-pressed="selectedId === point.id" @click="$emit('select', point.id)">
          <span class="point-index">{{ String(index + 1).padStart(2, '0') }}</span
          ><span>{{ point.name }}</span>
        </button>
      </li>
    </ol>
    <p v-if="!points.length" class="nav-empty">生成知识点后，目录会出现在这里。</p>
  </nav>
</template>

<style scoped>
.point-navigation {
  width: 264px;
  flex-shrink: 0;
  border-right: 1px solid var(--line);
  background: var(--soft);
  padding: 26px 14px;
  overflow-y: auto;
}
.eyebrow {
  padding: 0 12px 20px;
  display: flex;
  justify-content: space-between;
}
ol {
  list-style: none;
  padding: 0;
  margin: 0;
}
li + li {
  margin-top: 5px;
}
button {
  display: flex;
  align-items: baseline;
  gap: 12px;
  width: 100%;
  padding: 13px 12px;
  text-align: left;
  font-size: 13px;
  line-height: 1.7;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 9px;
  overflow-wrap: anywhere;
}
button:hover {
  background: #eaf0f5;
}
button[aria-pressed='true'] {
  background: var(--surface);
  border-color: var(--line);
  color: var(--accent);
  box-shadow: 0 2px 5px #24304004;
}
.point-index {
  font-size: 11px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.nav-empty {
  color: var(--muted);
  padding: 0 12px;
  font-size: 13px;
  line-height: 1.8;
}
@media (max-width: 640px) {
  .point-navigation {
    width: auto;
    max-height: 170px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
    padding: 14px;
  }
  .eyebrow {
    padding-bottom: 10px;
  }
  button {
    padding: 9px 12px;
  }
}
</style>
