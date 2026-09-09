<script setup lang="ts">
import AppIcon from '../../../shared/components/AppIcon.vue'
</script>

<template>
  <section class="materials-panel">
    <div class="materials-heading">
      <h2>让学习有据可循</h2>
      <p>为这门课程收集教材和笔记，让讲解连接到你的参考资料。</p>
    </div>
    <div class="upload-placeholder">
      <span class="empty-icon"><AppIcon name="file" /></span>
      <h3>课程资料库正在接入</h3>
      <p>后续支持 PDF、Markdown、TXT。上传后自动整理，讲解中可查看引用来源。</p>
      <button class="button secondary" disabled><AppIcon name="plus" />上传资料 · 待接入</button>
    </div>
    <p class="materials-note">
      资料依据会显示来源；额外的讲解与示例会标记为“AI 补充”。当前版本尚未处理或上传任何文件。
    </p>
  </section>
</template>

<style scoped>
.materials-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 32px;
}
.materials-heading h2 {
  font-size: 20px;
  margin-bottom: 9px;
}
.materials-heading p,
.materials-note {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
}
.upload-placeholder {
  border: 1px dashed #cad5df;
  border-radius: 12px;
  padding: 38px 20px;
  text-align: center;
  margin: 28px 0 20px;
  background: var(--soft);
}
.upload-placeholder h3 {
  font-size: 16px;
  margin: 16px 0 10px;
}
.upload-placeholder p {
  font-size: 13px;
  color: var(--muted);
  max-width: 370px;
  margin: 0 auto 23px;
  line-height: 1.8;
}
.upload-placeholder .empty-icon {
  margin: auto;
}
.materials-note {
  font-size: 12px;
}
@media (max-width: 640px) {
  .materials-panel {
    padding: 22px;
  }
}
</style>
