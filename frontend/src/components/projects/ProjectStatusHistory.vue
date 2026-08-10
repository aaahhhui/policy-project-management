<script setup lang="ts">
import { computed } from "vue";

import type { ProjectStatusHistoryDetail } from "../../api/projects";

const props = defineProps<{ entries: ProjectStatusHistoryDetail[] }>();

const actionLabels: Record<string, string> = {
  create: "创建", update: "更新", transition: "状态流转", correction: "更正", primary_entity_correction: "主申报企业更正",
};
const entries = computed(() => [...props.entries].sort((left, right) => {
  const occurred = right.occurred_at.localeCompare(left.occurred_at);
  return occurred || right.id - left.id;
}));

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "——";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
</script>

<template>
  <section class="project-history" aria-labelledby="project-history-title">
    <h2 id="project-history-title">变更历史</h2>
    <p v-if="!entries.length" class="empty">——</p>
    <ol v-else>
      <li v-for="entry in entries" :key="entry.id">
        <header><strong>{{ entry.actor.display_name }}</strong><span>{{ actionLabels[entry.action] ?? entry.action }}</span><time :datetime="entry.occurred_at">{{ entry.occurred_at }}</time></header>
        <dl>
          <div><dt>变更前</dt><dd>{{ display(entry.before_values) }}</dd></div>
          <div><dt>变更后</dt><dd>{{ display(entry.after_values) }}</dd></div>
          <div><dt>关联日期</dt><dd>{{ display(entry.related_date) }}</dd></div>
          <div v-if="entry.reason"><dt>原因</dt><dd>{{ entry.reason }}</dd></div>
        </dl>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.project-history{margin-top:1.25rem;padding-top:1.1rem;border-top:1px solid #d8e2ec;color:#29435f}.project-history h2{margin:0 0 .7rem;color:#1b3352;font:700 1.2rem/1.2 "Noto Serif SC","Songti SC",serif}.project-history ol{display:grid;gap:.7rem;margin:0;padding:0;list-style:none}.project-history li{padding:.75rem;border:1px solid #d8e2ec;background:#fff}.project-history header{display:flex;flex-wrap:wrap;gap:.5rem .8rem;align-items:baseline}.project-history header span{color:#174f7e;font-weight:700}.project-history time{margin-left:auto;color:#60758d;font-size:.82rem}.project-history dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem;margin:.7rem 0 0}.project-history dl div{min-width:0}.project-history dt{color:#60758d;font-size:.75rem;font-weight:700}.project-history dd{margin:.15rem 0 0;overflow-wrap:anywhere;font-size:.82rem}.empty{color:#60758d}@media(max-width:720px){.project-history dl{grid-template-columns:1fr}.project-history time{width:100%;margin-left:0}}
</style>
