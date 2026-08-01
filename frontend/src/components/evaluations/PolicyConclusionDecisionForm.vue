<script setup lang="ts">
import { computed, ref } from "vue";

import {
  adjustPolicyConclusion,
  type PolicyConclusion,
  type PolicyConclusionDecision,
} from "../../api/policies";

const props = defineProps<{
  policyId: number;
  currentConclusion: PolicyConclusion;
  hasPrimaryEntity: boolean;
}>();
const emit = defineEmits<{ decided: [decision: PolicyConclusionDecision] }>();

const conclusion = ref<PolicyConclusion>(props.currentConclusion);
const reason = ref("");
const error = ref("");
const saving = ref(false);
const missingPrimaryEntity = computed(
  () => conclusion.value === "recommend_apply" && !props.hasPrimaryEntity,
);
const options: Array<{ value: PolicyConclusion; label: string }> = [
  { value: "recommend_apply", label: "建议申报" },
  { value: "watch", label: "持续关注" },
  { value: "not_recommended", label: "暂不建议申报" },
  { value: "uncertain", label: "无法判断" },
];

async function submit(): Promise<void> {
  error.value = "";
  const trimmedReason = reason.value.trim();
  if (!trimmedReason) {
    error.value = "请填写调整原因";
    return;
  }
  if (missingPrimaryEntity.value) return;

  saving.value = true;
  try {
    const decision = await adjustPolicyConclusion(props.policyId, {
      conclusion: conclusion.value,
      reason: trimmedReason,
    });
    emit("decided", decision);
  } catch {
    error.value = "结论调整未完成，请稍后重试。";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <form data-conclusion-decision-form class="decision-form" @submit.prevent="submit">
    <label>
      调整后结论
      <select v-model="conclusion">
        <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <p v-if="missingPrimaryEntity" class="prerequisite" role="status">
      请先确认主申报企业，再调整为建议申报
    </p>
    <label>
      调整原因
      <textarea v-model="reason" rows="3" placeholder="请说明本次人工调整依据"></textarea>
    </label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="saving || missingPrimaryEntity">
      {{ saving ? "提交中…" : "确认调整" }}
    </button>
  </form>
</template>

<style scoped>
.decision-form{display:grid;gap:.8rem;margin-top:1rem;padding:1rem;border:1px solid #d6e1ec;background:#f9fbfd}.decision-form label{display:grid;gap:.35rem;color:#536b82;font-size:.8rem;font-weight:800}.decision-form select,.decision-form textarea{padding:.6rem;border:1px solid #b9c9d8;background:#fff;font:inherit}.decision-form p{margin:0}.decision-form p[role=alert],.prerequisite{color:#9b1c1c}.decision-form button{justify-self:start;padding:.58rem .9rem;color:#fff;border:1px solid #174f7e;background:#174f7e;font:inherit;font-weight:800}.decision-form button:disabled{cursor:not-allowed;opacity:.6}
</style>
