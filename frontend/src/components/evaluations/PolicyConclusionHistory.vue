<script setup lang="ts">
import { computed } from "vue";

import type { PolicyConclusionDecision } from "../../api/policies";

const props = defineProps<{ decisions: PolicyConclusionDecision[] }>();
const labels: Record<string, string> = {
  recommend_apply: "建议申报",
  watch: "持续关注",
  not_recommended: "暂不建议申报",
  uncertain: "无法判断",
};
const orderedDecisions = computed(() => [...props.decisions].sort(
  (left, right) => Date.parse(right.decided_at) - Date.parse(left.decided_at) || right.id - left.id,
));

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "long", timeStyle: "short" }).format(new Date(value));
}
</script>

<template>
  <section v-if="orderedDecisions.length" class="conclusion-history" aria-labelledby="conclusion-history-title">
    <h3 id="conclusion-history-title">结论历史</h3>
    <ol>
      <li v-for="decision in orderedDecisions" :key="decision.id" data-conclusion-history-item>
        <strong>{{ labels[decision.previous_conclusion] }} → {{ labels[decision.conclusion] }}</strong>
        <p v-if="decision.reason">原因：{{ decision.reason }}</p>
        <time :datetime="decision.decided_at">{{ formatTime(decision.decided_at) }}</time>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.conclusion-history{margin-top:1.2rem;padding-top:1rem;border-top:1px solid #d8e2ec}.conclusion-history h3{margin:.2rem 0 .8rem;font-family:"Noto Serif SC","Songti SC",serif}.conclusion-history ol{display:grid;gap:.65rem;margin:0;padding:0;list-style:none}.conclusion-history li{display:grid;gap:.25rem;padding:.75rem;border-left:3px solid #8fa3b8;background:#f7f9fb}.conclusion-history p{margin:0;color:#536b82}.conclusion-history time{color:#74899e;font-size:.78rem}
</style>
