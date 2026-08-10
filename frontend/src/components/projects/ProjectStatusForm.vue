<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { businessErrorMessage } from "../../api/errors";
import { transitionProject, type ProjectDetail, type ProjectStatus } from "../../api/projects";

const props = defineProps<{ project: ProjectDetail }>();
const emit = defineEmits<{ updated: [project: ProjectDetail] }>();
const transitions: Record<ProjectStatus, ProjectStatus[]> = { pending_application: ["submitted", "terminated"], submitted: ["succeeded", "rejected", "terminated"], succeeded: [], rejected: [], terminated: [] };
const labels: Record<ProjectStatus, string> = { pending_application: "待申报", submitted: "已提交", succeeded: "已成功", rejected: "未获批", terminated: "已终止" };
const targetStatus = ref<ProjectStatus>("submitted");
const submittedOn = ref("");
const resultOn = ref("");
const resultNote = ref("");
const terminationNote = ref("");
const saving = ref(false); const error = ref("");
const options = computed(() => transitions[props.project.status]);
const needsSubmission = computed(() => targetStatus.value === "submitted");
const needsResult = computed(() => targetStatus.value === "succeeded" || targetStatus.value === "rejected");
const needsTermination = computed(() => targetStatus.value === "terminated");
function sync(project: ProjectDetail): void { targetStatus.value = transitions[project.status][0] ?? project.status; submittedOn.value = project.submitted_on ?? ""; resultOn.value = project.result_on ?? ""; resultNote.value = project.result_note ?? ""; terminationNote.value = project.termination_note ?? ""; }
async function submit(): Promise<void> {
  if (saving.value || !options.value.length || (needsTermination.value && !terminationNote.value.trim())) { if (needsTermination.value && !terminationNote.value.trim()) error.value = "请填写终止备注。"; return; }
  saving.value = true; error.value = "";
  const payload = { expected_version: props.project.version, target_status: targetStatus.value } as { expected_version: number; target_status: ProjectStatus; submitted_on?: string | null; result_on?: string | null; result_note?: string | null; termination_note?: string | null };
  if (needsSubmission.value) payload.submitted_on = submittedOn.value || null;
  if (needsResult.value) { payload.result_on = resultOn.value || null; payload.result_note = resultNote.value.trim() || null; }
  if (needsTermination.value) payload.termination_note = terminationNote.value.trim() || null;
  try { emit("updated", await transitionProject(props.project.id, payload)); }
  catch (caught) { error.value = businessErrorMessage(caught, "状态变更未完成，请稍后重试。"); }
  finally { saving.value = false; }
}
watch(() => props.project, sync, { immediate: true, deep: true });
</script>

<template>
  <form v-if="options.length" class="project-status-form" @submit.prevent="submit">
    <label>目标状态<select v-model="targetStatus" aria-label="目标状态"><option v-for="option in options" :key="option" :value="option">{{ labels[option] }}</option></select></label>
    <label v-if="needsSubmission">提交日期<input v-model="submittedOn" type="date" aria-label="提交日期" required /></label>
    <template v-if="needsResult"><label>结果日期<input v-model="resultOn" type="date" aria-label="结果日期" required /></label><label>结果备注<textarea v-model="resultNote" aria-label="结果备注" maxlength="500" /></label></template>
    <label v-if="needsTermination">终止备注<textarea v-model="terminationNote" aria-label="终止备注" maxlength="2000" required /></label>
    <p v-if="error" role="alert">{{ error }}</p><button type="submit" :disabled="saving">{{ saving ? "正在提交……" : "变更状态" }}</button>
  </form>
</template>

<style scoped>
.project-status-form{display:grid;gap:.65rem}.project-status-form label{display:grid;gap:.28rem;font-size:.86rem;font-weight:700}.project-status-form input,.project-status-form select,.project-status-form textarea{box-sizing:border-box;width:100%;min-height:2.35rem;padding:.45rem .55rem;border:1px solid #b8c7d8;font:inherit}.project-status-form textarea{min-height:4.4rem}.project-status-form p{margin:0;padding:.7rem;color:#9b1c1c;background:#fff1f0}.project-status-form button{justify-self:start;min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:700}
</style>
