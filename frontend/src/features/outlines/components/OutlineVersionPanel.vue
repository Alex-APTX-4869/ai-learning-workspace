<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '../../../shared/components/AppIcon.vue'
import { useOutlineVersions } from '../useOutlineVersions'
import type { OutlineGenerationInput } from '../types'
import type { Course } from '../../courses/types'
import OutlineGenerationDialog from './OutlineGenerationDialog.vue'
import AddChapterDialog from './AddChapterDialog.vue'

const props = defineProps<{ courseId: number }>()
const emit = defineEmits<{ refresh: []; versionChanged: [course: Course] }>()
const {
  versions,
  selectedVersion,
  draftChapters,
  loading,
  selectingId,
  generating,
  loadError,
  selectionError,
  generationError,
  generationStatus,
  generationSaved,
  load,
  select,
  generate,
  cancel,
  clearGeneration,
} = useOutlineVersions(props.courseId)
const dialogOpen = ref(false)
const appendOpen = ref(false)
const selectedId = ref('')
const versionBusy = computed(() => generating.value || selectingId.value !== null || appendOpen.value)

async function appended() {
  appendOpen.value = false
  await load()
  emit('refresh')
}

watch(
  selectedVersion,
  (version) => {
    selectedId.value = version ? String(version.id) : ''
  },
  { immediate: true },
)

onMounted(load)

function openGenerator() {
  clearGeneration()
  dialogOpen.value = true
}

async function startGeneration(input: OutlineGenerationInput) {
  if (await generate(input)) emit('refresh')
}

async function changeVersion(event: Event) {
  const selectElement = event.target as HTMLSelectElement
  const previousId = selectedId.value
  const id = Number(selectElement.value)
  if (!Number.isInteger(id) || id < 1) {
    selectElement.value = previousId
    return
  }
  const course = await select(id)
  if (course) emit('versionChanged', course)
  else selectElement.value = previousId
}
</script>

<template>
  <section class="version-toolbar" aria-label="课程大纲版本">
    <div class="version-controls">
      <label for="outline-version-select">当前版本</label>
      <span v-if="loading" class="toolbar-status" role="status">
        <span class="spinner" />正在读取版本…
      </span>
      <select
        v-else
        id="outline-version-select"
        :value="selectedId"
        :disabled="versionBusy || !versions.length"
        @change="changeVersion"
      >
        <option v-if="!versions.length" value="">暂无版本</option>
        <option v-else-if="!selectedId" value="" disabled>选择一个版本</option>
        <option v-for="version in versions" :key="version.id" :value="version.id">
          V{{ version.version_number }} · {{ version.name }}
        </option>
      </select>
      <span v-if="selectingId !== null" class="toolbar-status" role="status">
        <span class="spinner" />正在切换…
      </span>
    </div>

    <button v-if="selectedVersion" type="button" class="regenerate-button" :disabled="versionBusy || loading" @click="appendOpen = true">＋ 增加章节</button>
    <button
      type="button"
      class="regenerate-button"
      :disabled="versionBusy || loading"
      @click="openGenerator"
    >
      <AppIcon name="sparkles" />{{ versions.length ? '重新生成课程大纲' : '生成课程大纲' }}
    </button>

    <div v-if="loadError" class="toolbar-error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" :disabled="loading" @click="load">重新读取</button>
    </div>
    <div v-if="selectionError" class="toolbar-error protected-error" role="alert">
      <div>
        <strong>版本没有切换</strong>
        <p>{{ selectionError }}</p>
      </div>
      <button type="button" aria-label="关闭版本切换错误" @click="selectionError = ''">
        知道了
      </button>
    </div>
  </section>

  <OutlineGenerationDialog
    :open="dialogOpen"
    :versions="versions"
    :chapters="draftChapters"
    :generating="generating"
    :saved="generationSaved"
    :status="generationStatus"
    :error="generationError"
    @close="dialogOpen = false"
    @cancel="cancel"
    @generate="startGeneration"
  />
  <AddChapterDialog v-if="appendOpen && selectedVersion" :course-id="courseId" :version-id="selectedVersion.id"
    @close="appendOpen = false" @published="appended" />
</template>

<style scoped>
.version-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px 13px;
  margin-bottom: 20px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
}
.version-controls {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 9px;
}
.version-controls label {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 10px;
}
select {
  width: min(390px, 100%);
  min-width: 150px;
  padding: 7px 30px 7px 9px;
  border: 1px solid #dce4eb;
  border-radius: 7px;
  background: var(--soft);
  color: var(--ink);
  font: inherit;
  font-size: 11px;
}
.toolbar-status {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 10px;
}
.toolbar-status .spinner {
  width: 12px;
  height: 12px;
}
.regenerate-button {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--accent);
  font-size: 10px;
}
.regenerate-button:hover:not(:disabled) {
  background: var(--soft);
}
.regenerate-button .app-icon {
  width: 13px;
  height: 13px;
}
.toolbar-error {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 9px 10px;
  border-top: 1px solid #f0d9d7;
  color: var(--danger);
  font-size: 10px;
  line-height: 1.65;
}
.toolbar-error button {
  flex-shrink: 0;
  padding: 3px 4px;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 10px;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.toolbar-error strong {
  font-size: 11px;
}
.toolbar-error p {
  margin-top: 2px;
}
.protection-note {
  color: #7e6667;
}
@media (max-width: 620px) {
  .version-toolbar,
  .version-controls {
    align-items: stretch;
    flex-direction: column;
  }
  .version-toolbar {
    flex-wrap: nowrap;
  }
  .version-controls {
    width: 100%;
    gap: 6px;
  }
  select {
    width: 100%;
  }
  .regenerate-button {
    align-self: flex-start;
    padding-inline: 1px;
  }
  .toolbar-error {
    align-items: flex-start;
  }
}
</style>
