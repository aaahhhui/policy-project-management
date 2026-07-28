<script setup lang="ts">
import { ref } from "vue";

import type { EvaluationBatch } from "../../api/evaluations";

const props = defineProps<{ evaluations: EvaluationBatch[] }>();
const expanded = ref(false);

const statusLabels: Record<string, string> = {
  pending: "等待评估",
  running: "评估中",
  succeeded: "已完成",
  failed: "评估失败",
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
</script>

<template>
  <section v-if="props.evaluations.length" class="evaluation-history">
    <button
      type="button"
      :aria-expanded="expanded"
      aria-controls="evaluation-history-list"
      @click="expanded = !expanded"
    >
      <span>历史评估</span>
      <span>{{ props.evaluations.length }} 个批次 {{ expanded ? "收起" : "展开" }}</span>
    </button>
    <ol v-show="expanded" id="evaluation-history-list">
      <li v-for="evaluation in props.evaluations" :key="evaluation.id">
        <div>
          <strong>批次 #{{ evaluation.id }}</strong>
          <span :data-status="evaluation.status">{{ statusLabels[evaluation.status] ?? evaluation.status }}</span>
        </div>
        <time :datetime="evaluation.created_at">{{ formatTime(evaluation.created_at) }}</time>
        <p v-if="evaluation.summary">{{ evaluation.summary }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.evaluation-history { margin-top: 1rem; border-top: 1px solid #dce5ed; }
button { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 0 0; color: #315671; border: 0; background: transparent; font: inherit; font-weight: 800; cursor: pointer; }
button span:last-child { color: #778a9c; font-size: .72rem; font-weight: 600; }
ol { margin: .9rem 0 0; padding: 0; list-style: none; border: 1px solid #dce5ed; }
li { display: grid; grid-template-columns: minmax(10rem, .8fr) auto minmax(14rem, 1.4fr); align-items: center; gap: 1rem; padding: .75rem .9rem; }
li + li { border-top: 1px solid #e7edf2; }
li div { display: flex; align-items: center; gap: .6rem; }
li span, time { color: #74889a; font-size: .75rem; }
li p { margin: 0; color: #405a70; font-size: .8rem; }
@media (max-width: 680px) { li { grid-template-columns: 1fr; gap: .3rem; } }
</style>
