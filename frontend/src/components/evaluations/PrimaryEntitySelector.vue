<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { selectPrimaryEntity, type PrimaryEntityDecision } from "../../api/evaluations";

const props = defineProps<{ policyId: number; candidates: Array<{ entity_seed_code: string; label: string }>; current: PrimaryEntityDecision | null }>();
const emit = defineEmits<{ selected: [] }>();
const selected = ref(props.current?.entity_seed_code ?? props.candidates[0]?.entity_seed_code ?? "");
const reason = ref("");
const error = ref("");
const unchanged = computed(
  () => Boolean(props.current && selected.value === props.current.entity_seed_code),
);

watch(
  () => props.current?.entity_seed_code,
  (entitySeedCode) => {
    if (entitySeedCode) selected.value = entitySeedCode;
  },
);

async function submit() {
  error.value = "";
  const changing = Boolean(props.current && selected.value !== props.current.entity_seed_code);
  if (changing && !reason.value.trim()) {
    error.value = "切换主申报企业必须填写原因";
    return;
  }
  try {
    await selectPrimaryEntity(props.policyId, { entity_seed_code: selected.value, reason: reason.value.trim() || null });
    emit("selected");
  } catch {
    error.value = "主申报企业未保存，请刷新后重试。";
  }
}
</script>

<template>
  <form class="primary-selector" @submit.prevent="submit">
    <p>人工确定</p><h3>主申报企业</h3>
    <label v-for="candidate in candidates" :key="candidate.entity_seed_code" class="candidate">
      <input v-model="selected" type="radio" :value="candidate.entity_seed_code" />
      <span>{{ candidate.label }}</span>
    </label>
    <p v-if="current" class="current-selection">
      当前主申报企业：{{ current.entity_legal_name }}。如需切换，请选择其他企业并填写原因。
    </p>
    <label class="reason">切换原因<textarea v-model="reason" rows="2" /></label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="unchanged">
      {{ unchanged ? "当前企业已确认" : current ? "更新主申报企业" : "确定主申报企业" }}
    </button>
  </form>
</template>

<style scoped>
.primary-selector{margin-top:1rem;padding:1rem;border:1px solid #d6e1ec;background:#fff}.primary-selector>p:first-child{margin:0;color:#74899e;font-size:.72rem}.primary-selector h3{margin:.25rem 0 .8rem;font-family:"Noto Serif SC","Songti SC",serif}.candidate{display:flex;gap:.55rem;padding:.55rem;border-top:1px solid #e3ebf3}.current-selection{margin:.8rem 0 0;padding:.65rem .75rem;color:#315671;background:#eef5fa}.reason{display:grid;gap:.3rem;margin-top:.8rem;color:#60758d;font-size:.76rem}textarea{padding:.55rem;border:1px solid #b9c9d8;font:inherit}.primary-selector p[role=alert]{color:#9b1c1c}.primary-selector button{margin-top:.8rem;padding:.55rem .85rem;border:1px solid #174f7e;background:#174f7e;color:#fff;font-weight:700}.primary-selector button:disabled{cursor:not-allowed;opacity:.55}
</style>
