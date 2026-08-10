<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { businessErrorMessage } from "../../api/errors";
import { correctProjectPrimaryEntity, correctProjectStatus, type ProjectDetail, type ProjectStatus } from "../../api/projects";

const props = defineProps<{ project: ProjectDetail; mode: "status" | "primary-entity" }>();
const emit = defineEmits<{ updated: [project: ProjectDetail] }>();
const labels: Record<ProjectStatus, string> = { pending_application: "待申报", submitted: "已提交", succeeded: "已成功", rejected: "未获批", terminated: "已终止" };
const resultStatuses: ProjectStatus[] = ["succeeded", "rejected"];
const preTerminationStatus = computed(() => [...props.project.status_history].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at) || b.id - a.id).find((entry) => entry.new_status === "terminated")?.previous_status ?? null);
const statusOptions = computed<ProjectStatus[]>(() => {
  if (props.project.status === "terminated") return preTerminationStatus.value ? [preTerminationStatus.value] : [];
  if (resultStatuses.includes(props.project.status)) return ["submitted", ...resultStatuses.filter((status) => status !== props.project.status)];
  return [];
});
const targetStatus = ref<ProjectStatus>(statusOptions.value[0] ?? "submitted");
const resultOn = ref(props.project.result_on ?? ""); const resultNote = ref(props.project.result_note ?? ""); const reason = ref(""); const primaryEntityId = ref(String(props.project.primary_entity_decision_id));
const saving = ref(false); const error = ref("");
const hasStatusPermission = computed(() => props.project.capabilities.can_correct_status && statusOptions.value.length > 0);
const hasPrimaryPermission = computed(() => props.project.capabilities.can_correct_primary_entity);
const needsResult = computed(() => resultStatuses.includes(targetStatus.value));
function needsClearConfirmation(): boolean { return (targetStatus.value === "submitted" && Boolean(props.project.result_on || props.project.result_note)) || (props.project.status === "terminated" && Boolean(props.project.termination_note)); }
async function submitStatus(): Promise<void> {
  if (saving.value || !hasStatusPermission.value) return;
  if (needsClearConfirmation() && !window.confirm("此更正会清除当前结果或终止记录，是否继续？")) return;
  saving.value = true; error.value = "";
  try { emit("updated", await correctProjectStatus(props.project.id, { expected_version: props.project.version, target_status: targetStatus.value, submitted_on: props.project.submitted_on ?? null, result_on: needsResult.value ? resultOn.value || null : null, result_note: needsResult.value ? resultNote.value.trim() || null : null, termination_note: null, reason: reason.value.trim() || null })); }
  catch (caught) { error.value = businessErrorMessage(caught, "状态更正未完成，请稍后重试。"); }
  finally { saving.value = false; }
}
async function submitPrimary(): Promise<void> {
  const id = Number(primaryEntityId.value); if (saving.value || !hasPrimaryPermission.value || !Number.isInteger(id) || id < 1) return;
  saving.value = true; error.value = "";
  try { emit("updated", await correctProjectPrimaryEntity(props.project.id, { expected_version: props.project.version, primary_entity_decision_id: id, reason: reason.value.trim() || null })); }
  catch (caught) { error.value = businessErrorMessage(caught, "主申报企业更正未完成，请稍后重试。"); }
  finally { saving.value = false; }
}
watch(() => props.project, (project) => {
  targetStatus.value = statusOptions.value[0] ?? "submitted";
  resultOn.value = project.result_on ?? ""; resultNote.value = project.result_note ?? "";
  primaryEntityId.value = String(project.primary_entity_decision_id); reason.value = "";
}, { deep: true });
</script>

<template>
  <form v-if="mode === 'status' && hasStatusPermission" class="project-correction" @submit.prevent="submitStatus">
    <label>更正目标状态<select v-model="targetStatus" aria-label="更正目标状态"><option v-for="option in statusOptions" :key="option" :value="option">{{ labels[option] }}</option></select></label>
    <template v-if="needsResult"><label>结果日期<input v-model="resultOn" type="date" aria-label="结果日期" required /></label><label>结果备注<textarea v-model="resultNote" aria-label="结果备注" maxlength="500" /></label></template>
    <label>更正原因（可选）<textarea v-model="reason" aria-label="更正原因" maxlength="1000" /></label><p v-if="error" role="alert">{{ error }}</p><button type="submit" :disabled="saving">确认更正</button>
  </form>
  <form v-else-if="mode === 'primary-entity' && hasPrimaryPermission" class="project-correction" @submit.prevent="submitPrimary">
    <label>主申报企业决定 ID<input v-model="primaryEntityId" type="number" min="1" aria-label="主申报企业决定 ID" required /></label><label>更正原因（可选）<textarea v-model="reason" aria-label="更正原因" maxlength="1000" /></label><p v-if="error" role="alert">{{ error }}</p><button type="submit" :disabled="saving">确认更正</button>
  </form>
</template>

<style scoped>
.project-correction{display:grid;gap:.65rem}.project-correction label{display:grid;gap:.28rem;font-size:.86rem;font-weight:700}.project-correction input,.project-correction select,.project-correction textarea{box-sizing:border-box;width:100%;min-height:2.35rem;padding:.45rem .55rem;border:1px solid #b8c7d8;font:inherit}.project-correction textarea{min-height:4.4rem}.project-correction p{margin:0;padding:.7rem;color:#9b1c1c;background:#fff1f0}.project-correction button{justify-self:start;min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:700}
</style>
