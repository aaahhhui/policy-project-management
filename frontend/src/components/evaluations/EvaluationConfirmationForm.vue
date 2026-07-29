<script setup lang="ts">
import { computed, ref } from "vue";

import { confirmEvaluation, type EntityEvaluation, type EvaluationBatch } from "../../api/evaluations";

type ConfirmableEvaluation = Pick<EvaluationBatch, "id" | "conclusion" | "summary" | "key_conditions"> & { entities: EntityEvaluation[] };
const props = defineProps<{ evaluation: ConfirmableEvaluation }>();
const emit = defineEmits<{ confirmed: [] }>();
const entities = ref(props.evaluation.entities.map((item) => ({ ...item })));
const reason = ref("");
const error = ref("");
const saving = ref(false);
const changed = computed(() => JSON.stringify(entities.value) !== JSON.stringify(props.evaluation.entities));

async function submit() {
  error.value = "";
  if (changed.value && !reason.value.trim()) {
    error.value = "修改 AI 建议后必须填写原因";
    return;
  }
  if (!props.evaluation.conclusion || !props.evaluation.summary) return;
  saving.value = true;
  try {
    await confirmEvaluation(props.evaluation.id, {
      conclusion: props.evaluation.conclusion,
      summary: props.evaluation.summary,
      key_conditions: props.evaluation.key_conditions ?? [],
      entities: entities.value,
      change_reason: reason.value.trim() || null,
    });
    emit("confirmed");
  } catch {
    error.value = "确认未完成，请刷新后重试。";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <form class="confirmation-form" @submit.prevent="submit">
    <header><div><p>负责人复核</p><h3>确认评估结论</h3></div><span>AI 原始结果保持不变</span></header>
    <div class="score-grid">
      <label v-for="entity in entities" :key="entity.entity_seed_code">
        <span>{{ entity.entity_seed_code }}</span>
        <input v-model.number="entity.score" :data-score="entity.entity_seed_code" type="number" min="0" max="100" />
      </label>
    </div>
    <label class="reason">修改原因<textarea v-model="reason" rows="2" placeholder="仅在修改 AI 建议时必填" /></label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="saving">{{ saving ? "确认中…" : "确认评估" }}</button>
  </form>
</template>

<style scoped>
.confirmation-form{margin-top:1rem;padding:1rem;border:1px solid #d6e1ec;border-left:4px solid #d4a449;background:#f9fbfd}.confirmation-form header{display:flex;justify-content:space-between;gap:1rem}.confirmation-form header p{margin:0;color:#74899e;font-size:.72rem}.confirmation-form h3{margin:.2rem 0;font-family:"Noto Serif SC","Songti SC",serif}.confirmation-form header span{color:#60758d;font-size:.75rem}.score-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem;margin:1rem 0}.score-grid label,.reason{display:grid;gap:.3rem;color:#60758d;font-size:.76rem;font-weight:700}input,textarea{padding:.55rem;border:1px solid #b9c9d8;font:inherit}.confirmation-form p[role=alert]{color:#9b1c1c}.confirmation-form button{margin-top:.8rem;padding:.55rem .85rem;border:1px solid #174f7e;background:#174f7e;color:#fff;font-weight:700}@media(max-width:700px){.score-grid{grid-template-columns:1fr}}
</style>
