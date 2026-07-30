<script setup lang="ts">
import type { EvaluationBatch } from "../../api/evaluations";
import EntityEvaluationCard from "./EntityEvaluationCard.vue";

const props = defineProps<{ evaluation: EvaluationBatch }>();

function formatTime(value: string | null): string {
  if (!value) return "尚未生成";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function entityName(seedCode: string): string {
  const profile = props.evaluation.profile_snapshot.find(
    (item) => item.seed_code === seedCode,
  );
  return String(profile?.legal_name ?? "");
}
</script>

<template>
  <section class="evaluation-summary" aria-labelledby="evaluation-title">
    <header class="summary-header">
      <div>
        <p class="eyebrow">模型辅助分析 · 负责人确认前仅供参考</p>
        <h2 id="evaluation-title">企业匹配评估</h2>
      </div>
      <dl>
        <div><dt>生成时间</dt><dd>{{ formatTime(props.evaluation.finished_at) }}</dd></div>
        <div><dt>评估批次</dt><dd>批次 #{{ props.evaluation.id }}</dd></div>
      </dl>
    </header>

    <div class="summary-copy">
      <section>
        <h3>模型摘要</h3>
        <p>{{ props.evaluation.summary }}</p>
      </section>
      <section>
        <h3>关键申报条件</h3>
        <ul><li v-for="condition in props.evaluation.key_conditions ?? []" :key="condition">{{ condition }}</li></ul>
      </section>
    </div>

    <div class="entity-grid" aria-label="三经营主体评估结果">
      <EntityEvaluationCard
        v-for="entity in props.evaluation.entities"
        :key="entity.entity_seed_code"
        :evaluation="entity"
        :entity-name="entityName(entity.entity_seed_code)"
      />
    </div>
  </section>
</template>

<style scoped>
.evaluation-summary { color: #203c56; }
.summary-header { display: flex; align-items: end; justify-content: space-between; gap: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid #1e568c; }
.eyebrow { margin: 0 0 .3rem; color: #6b8197; font-size: .72rem; font-weight: 800; letter-spacing: .07em; }
h2 { margin: 0; font: 700 1.35rem/1.35 "Noto Serif SC", "Songti SC", serif; }
dl { display: flex; gap: 1.25rem; margin: 0; }
dt { color: #788b9e; font-size: .68rem; }
dd { margin: .2rem 0 0; font-size: .78rem; font-weight: 800; }
.summary-copy { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(16rem, .65fr); gap: 1.4rem; padding: 1.1rem 0; }
.summary-copy section + section { padding-left: 1.4rem; border-left: 1px solid #dce5ed; }
.summary-copy h3 { margin: 0 0 .4rem; color: #6b8197; font-size: .75rem; }
.summary-copy p, .summary-copy ul { margin: 0; color: #2c465f; font-size: .9rem; line-height: 1.7; }
.summary-copy ul { padding-left: 1.1rem; }
.entity-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .9rem; }
@media (max-width: 850px) { .entity-grid { grid-template-columns: 1fr; }.summary-copy { grid-template-columns: 1fr; }.summary-copy section + section { padding: 0; border: 0; }.summary-header { align-items: start; flex-direction: column; } }
@media (max-width: 520px) { dl { align-items: start; flex-direction: column; gap: .55rem; } }
</style>
