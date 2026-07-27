<script setup lang="ts">
import type { PolicyVersion } from "../../api/policies";
defineProps<{ versions: PolicyVersion[] }>();
function formatTime(value: string) { return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
</script>

<template>
  <section aria-labelledby="versions-title">
    <h2 id="versions-title">版本历史</h2>
    <ol class="versions">
      <li v-for="version in versions" :key="version.id">
        <strong>版本 {{ version.version_number }}</strong>
        <time :datetime="version.collected_at">{{ formatTime(version.collected_at) }}</time>
        <a :href="version.snapshot_url">查看快照</a>
      </li>
    </ol>
  </section>
</template>

<style scoped>
h2 { font: 700 1.15rem/1.4 "Noto Serif SC", "Songti SC", serif; }.versions { padding-left: 1.25rem; }.versions li { display: grid; grid-template-columns: 8rem 1fr auto; gap: 1rem; padding: .75rem 0; border-bottom: 1px solid #e2eaf2; }.versions time { color: #657a91; }.versions a { color: #14558c; }@media (max-width: 600px) { .versions li { grid-template-columns: 1fr; gap: .25rem; } }
</style>
