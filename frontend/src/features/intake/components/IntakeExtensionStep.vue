<script setup lang="ts">
import type { IntakeRead } from '../types'
defineProps<{proposal: NonNullable<IntakeRead['extension_proposal']>; busy: boolean; answered: number; total: number}>()
defineEmits<{decide:[approve:boolean]}>()
</script>
<template>
  <section class="extension-step">
    <p class="eyebrow">已经回答 {{ answered }} / {{ total }} 题</p>
    <h2>还想向你确认一件事</h2>
    <p>{{ proposal.reason }}</p>
    <div class="request"><strong>还不确定的地方</strong><p>{{ proposal.uncertainty }}</p>
      <strong>准备补问</strong><p>{{ proposal.question.text }}</p></div>
    <p class="note">同意后增加 1 题。也可以直接继续，未确认的信息会保留为未知。</p>
    <div class="actions"><button class="button secondary" :disabled="busy" @click="$emit('decide',false)">不补问，按已有信息继续</button>
      <button class="button primary" :disabled="busy" @click="$emit('decide',true)">同意补问 1 题</button></div>
  </section>
</template>
<style scoped>
.extension-step{max-width:760px;margin:auto;padding:24px 0;}h2{font-size:25px;margin:15px 0;}p{line-height:1.9;white-space:pre-wrap;}.request{padding:22px;border:1px solid var(--line);border-radius:14px;margin:24px 0;background:var(--surface);}.request strong{font-size:12px;color:var(--accent);}.request p{margin:8px 0 18px;}.note{font-size:12px;color:var(--muted);}.actions{display:flex;gap:12px;justify-content:flex-end;flex-wrap:wrap;margin-top:24px;}
</style>
