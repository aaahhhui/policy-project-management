<script setup lang="ts">
import type { EntityEvaluation } from "../../api/evaluations";

const props = defineProps<{ evaluation: EntityEvaluation }>();

const entityNames: Record<string, string> = {
  "ENTITY-BEIJING": "北京适创科技有限公司",
  "ENTITY-SUZHOU": "苏州数算软云科技有限公司",
  "ENTITY-SHENZHEN": "深圳适创腾扬科技有限公司",
};
const matchLabels: Record<string, string> = {
  high: "高匹配",
  medium: "中等匹配",
  low: "低匹配",
  uncertain: "待核验",
};
</script>

<template>
  <article class="entity-card" :data-match="props.evaluation.match_level">
    <header>
      <div>
        <p class="entity-code">{{ props.evaluation.entity_seed_code }}</p>
        <h3>{{ entityNames[props.evaluation.entity_seed_code] ?? props.evaluation.entity_seed_code }}</h3>
      </div>
      <span class="match-level">{{ matchLabels[props.evaluation.match_level] ?? props.evaluation.match_level }}</span>
    </header>

    <div class="evidence-track">
      <section>
        <h4>匹配依据</h4>
        <ul><li v-for="item in props.evaluation.evidence" :key="item">{{ item }}</li></ul>
      </section>
      <section v-if="props.evaluation.unmet_conditions.length">
        <h4>待满足条件</h4>
        <ul><li v-for="item in props.evaluation.unmet_conditions" :key="item">{{ item }}</li></ul>
      </section>
      <section v-if="props.evaluation.risks.length" class="risk-list">
        <h4>风险提示</h4>
        <ul><li v-for="item in props.evaluation.risks" :key="item">{{ item }}</li></ul>
      </section>
    </div>

    <footer><span>建议动作</span><strong>{{ props.evaluation.recommended_action }}</strong></footer>
  </article>
</template>

<style scoped>
.entity-card { min-width: 0; border: 1px solid #d8e2ec; border-top: 4px solid #4b7298; background: #fff; }
.entity-card[data-match="high"] { border-top-color: #2f765f; }
.entity-card[data-match="uncertain"] { border-top-color: #b6832d; }
header { display: flex; align-items: start; justify-content: space-between; gap: .8rem; padding: 1rem 1rem .85rem; border-bottom: 1px solid #e5edf4; }
.entity-code { margin: 0 0 .25rem; color: #7a8da1; font: 700 .68rem/1.2 ui-monospace, "SFMono-Regular", Consolas, monospace; letter-spacing: .06em; }
h3 { margin: 0; color: #183753; font: 700 1rem/1.45 "Noto Serif SC", "Songti SC", serif; }
.match-level { flex: none; padding: .2rem .5rem; color: #365a77; border: 1px solid #b9cad8; background: #f4f8fb; font-size: .72rem; font-weight: 800; }
.evidence-track { padding: .95rem 1rem; }
section + section { margin-top: .85rem; padding-top: .85rem; border-top: 1px dashed #dce5ed; }
h4 { margin: 0 0 .38rem; color: #718397; font-size: .72rem; letter-spacing: .04em; }
ul { margin: 0; padding-left: 1.05rem; color: #334b63; font-size: .84rem; line-height: 1.65; }
.risk-list li { color: #8a4c31; }
footer { display: grid; gap: .25rem; min-height: 3.7rem; padding: .75rem 1rem; border-top: 1px solid #e5edf4; background: #f7f9fb; }
footer span { color: #718397; font-size: .7rem; }
footer strong { color: #213f5b; font-size: .84rem; line-height: 1.45; }
</style>
