<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; labelledby: string; wide?: boolean; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const element = ref<HTMLDialogElement | null>(null)

function sync() {
  if (!element.value) return
  if (props.open && !element.value.open) element.value.showModal()
  if (!props.open && element.value.open) element.value.close()
  document.documentElement.classList.toggle('has-dialog', !!document.querySelector('dialog[open]'))
}
function close() {
  if (!props.busy) emit('close')
}
function backdrop(event: MouseEvent) {
  if (event.target !== element.value || !element.value) return
  const box = element.value.getBoundingClientRect()
  if (
    event.clientX < box.left ||
    event.clientX > box.right ||
    event.clientY < box.top ||
    event.clientY > box.bottom
  )
    close()
}
onMounted(sync)
watch(() => props.open, sync, { flush: 'post' })
onBeforeUnmount(() => {
  element.value?.close()
  document.documentElement.classList.toggle('has-dialog', !!document.querySelector('dialog[open]'))
})
</script>

<template>
  <Teleport to="body">
    <!-- 原生 dialog 提供焦点限制、Esc 关闭和关闭后恢复焦点。 -->
    <dialog
      ref="element"
      class="dialog"
      :class="{ 'dialog-wide': wide }"
      :aria-labelledby="labelledby"
      @cancel.prevent="close"
      @click="backdrop"
    >
      <slot />
    </dialog>
  </Teleport>
</template>

<style scoped>
.dialog {
  padding: 0;
  border: 1px solid #fff;
  border-radius: 20px;
  width: min(520px, calc(100vw - 32px));
  max-height: calc(100dvh - 48px);
  color: var(--ink);
  background: var(--surface);
  box-shadow: 0 32px 100px #27334626;
}
.dialog::backdrop {
  background: #26344842;
  backdrop-filter: blur(7px);
}
.dialog-wide {
  width: min(1160px, calc(100vw - 64px));
  height: min(800px, calc(100dvh - 80px));
  overflow: hidden;
}
@media (max-width: 640px) {
  .dialog-wide {
    width: calc(100vw - 16px);
    height: calc(100dvh - 24px);
    max-height: calc(100dvh - 24px);
    border-radius: 14px;
  }
}
</style>
