<script setup lang="ts">
import type { PolicyAttachment } from "../../api/policies";
defineProps<{ attachments: PolicyAttachment[] }>();
</script>

<template>
  <section aria-labelledby="attachments-title">
    <h2 id="attachments-title">附件</h2>
    <p v-if="attachments.length === 0" class="muted">该版本没有附件。</p>
    <ul v-else class="attachment-list">
      <li v-for="attachment in attachments" :key="attachment.id">
        <a v-if="attachment.download_url" :href="attachment.download_url">{{ attachment.display_name }}</a>
        <span v-else>{{ attachment.display_name }}</span>
        <small v-if="attachment.status === 'failed'">下载失败：{{ attachment.error_message }}</small>
        <a class="source-link" :href="attachment.source_url" target="_blank" rel="noreferrer">原始地址</a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
h2 { font: 700 1.15rem/1.4 "Noto Serif SC", "Songti SC", serif; }.muted { color: #6a7e95; }.attachment-list { display: grid; gap: .65rem; padding: 0; list-style: none; }.attachment-list li { display: flex; flex-wrap: wrap; gap: .55rem 1rem; padding: .8rem 0; border-bottom: 1px solid #e2eaf2; }.attachment-list a { color: #14558c; }.attachment-list small { width: 100%; color: #9b1c1c; }.source-link { margin-left: auto; font-size: .8rem; }
</style>
