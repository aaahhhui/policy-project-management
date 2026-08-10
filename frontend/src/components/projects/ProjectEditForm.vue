<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";

import { businessErrorMessage } from "../../api/errors";
import { updateProject, type ProjectDetail, type ProjectUpdateInput } from "../../api/projects";

const props = defineProps<{ project: ProjectDetail }>();
const emit = defineEmits<{ updated: [project: ProjectDetail]; reload: [] }>();
const saving = ref(false);
const error = ref("");
const conflict = ref(false);
const form = reactive({ name: "", deadline_on: "", liaison_user_id: "", member_user_ids: "", submitted_on: "", result_on: "", progress_note: "", result_note: "", termination_note: "" });
const liaisonFields = ["submitted_on", "result_on", "progress_note", "result_note", "termination_note"] as const;
const ownerFields = ["name", "deadline_on", "liaison_user_id", "member_user_ids", ...liaisonFields] as const;
const isOwner = computed(() => props.project.capabilities.can_edit_project);

function syncForm(project: ProjectDetail): void {
  form.name = project.name; form.deadline_on = project.deadline_on ?? ""; form.liaison_user_id = String(project.liaison_user_id);
  form.member_user_ids = project.members.map((member) => member.user_id).join(","); form.submitted_on = project.submitted_on ?? "";
  form.result_on = project.result_on ?? ""; form.progress_note = project.progress_note ?? ""; form.result_note = project.result_note ?? ""; form.termination_note = project.termination_note ?? "";
}
function normalize(value: string): string | null { return value.trim() || null; }
function memberIds(): number[] { return [...new Set(form.member_user_ids.split(",").map((value) => Number(value.trim())).filter((value) => Number.isInteger(value) && value > 0))]; }
function isVersionConflict(caught: unknown): boolean {
  const detail = (caught as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail;
  return detail?.code === "project_version_conflict";
}
async function submit(): Promise<void> {
  if (saving.value) return;
  saving.value = true; error.value = ""; conflict.value = false;
  const source = isOwner.value ? ownerFields : liaisonFields;
  const values = {
    name: normalize(form.name), deadline_on: form.deadline_on || null, liaison_user_id: Number(form.liaison_user_id) || null, member_user_ids: memberIds(),
    submitted_on: form.submitted_on || null, result_on: form.result_on || null, progress_note: normalize(form.progress_note), result_note: normalize(form.result_note), termination_note: normalize(form.termination_note),
  };
  const payload = Object.fromEntries(source.map((field) => [field, values[field]])) as Omit<ProjectUpdateInput, "expected_version">;
  try { emit("updated", await updateProject(props.project.id, { expected_version: props.project.version, ...payload })); }
  catch (caught) { conflict.value = isVersionConflict(caught); error.value = businessErrorMessage(caught, "项目维护未完成，请稍后重试。"); }
  finally { saving.value = false; }
}

watch(() => props.project, syncForm, { immediate: true, deep: true });
</script>

<template>
  <form class="project-edit-form" @submit.prevent="submit">
    <label v-if="isOwner">项目名称<input v-model="form.name" aria-label="项目名称" maxlength="255" /></label>
    <label v-if="isOwner">截止日期<input v-model="form.deadline_on" type="date" aria-label="项目截止日期" /></label>
    <label v-if="isOwner">项目对接人<input v-model="form.liaison_user_id" type="number" min="1" aria-label="项目对接人" /></label>
    <label v-if="isOwner">成员 ID（以逗号分隔）<input v-model="form.member_user_ids" aria-label="项目成员" /></label>
    <label>提交日期<input v-model="form.submitted_on" type="date" aria-label="提交日期" /></label>
    <label>结果日期<input v-model="form.result_on" type="date" aria-label="结果日期" /></label>
    <label>进展备注<textarea v-model="form.progress_note" aria-label="进展备注" maxlength="2000" /></label>
    <label>结果备注<textarea v-model="form.result_note" aria-label="结果备注" maxlength="500" /></label>
    <label>终止备注<textarea v-model="form.termination_note" aria-label="终止备注" maxlength="2000" /></label>
    <p v-if="error" role="alert" class="error">{{ error }} <button v-if="conflict" type="button" data-reload-project @click="emit('reload')">重新加载</button></p>
    <button type="submit" :disabled="saving">{{ saving ? "正在保存……" : "保存项目维护" }}</button>
  </form>
</template>

<style scoped>
.project-edit-form{display:grid;gap:.65rem}.project-edit-form label{display:grid;gap:.28rem;font-size:.86rem;font-weight:700}.project-edit-form input,.project-edit-form textarea{box-sizing:border-box;width:100%;min-height:2.35rem;padding:.45rem .55rem;border:1px solid #b8c7d8;font:inherit}.project-edit-form textarea{min-height:4.4rem;resize:vertical}.project-edit-form button{justify-self:start;min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:700}.error{margin:0;padding:.7rem;color:#9b1c1c;background:#fff1f0}.error button{margin-left:.5rem;color:#8a1c1c;border-color:#d69a98;background:#fff}button:disabled{opacity:.6}
</style>
