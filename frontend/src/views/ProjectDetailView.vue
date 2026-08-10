<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { getProject, type ProjectDetail } from "../api/projects";
import ProjectCorrectionDialog from "../components/projects/ProjectCorrectionDialog.vue";
import ProjectEditForm from "../components/projects/ProjectEditForm.vue";
import ProjectStatusForm from "../components/projects/ProjectStatusForm.vue";
import ProjectStatusHistory from "../components/projects/ProjectStatusHistory.vue";

const route = useRoute();
const project = ref<ProjectDetail | null>(null);
const loading = ref(true);
const error = ref("");
const mobile = ref(false);
let mediaQuery: MediaQueryList | null = null;

const statusLabels: Record<string, string> = { pending_application: "待申报", submitted: "已提交", succeeded: "已成功", rejected: "未获批", terminated: "已终止" };
const conclusionLabels: Record<string, string> = { recommend_apply: "建议申报", watch: "持续关注", not_recommended: "暂不建议申报", uncertain: "无法判断" };
const canShowMutations = computed(() => !mobile.value && project.value !== null && (
  project.value.capabilities.can_edit_project || project.value.capabilities.can_update_progress || project.value.capabilities.can_transition || project.value.capabilities.can_correct_status
));

function display(value: string | null | undefined): string { return value?.trim() || "——"; }
function updateMobile(): void { mobile.value = mediaQuery?.matches ?? false; }
function replaceProject(updated: ProjectDetail): void { project.value = updated; }
async function load(): Promise<void> {
  loading.value = true; error.value = "";
  try { project.value = await getProject(Number(route.params.id)); }
  catch { error.value = "无法加载项目详情，请稍后重试。"; }
  finally { loading.value = false; }
}

onMounted(() => { mediaQuery = window.matchMedia("(max-width: 720px)"); updateMobile(); mediaQuery.addEventListener("change", updateMobile); });
watch(() => route.params.id, () => { void load(); }, { immediate: true });
onBeforeUnmount(() => mediaQuery?.removeEventListener("change", updateMobile));
</script>

<template>
  <section class="project-detail" aria-labelledby="project-detail-title">
    <p v-if="loading" role="status">正在加载项目详情……</p>
    <p v-else-if="error" class="error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
    <template v-else-if="project">
      <header class="heading"><p class="eyebrow">项目管理 · 可追溯台账</p><div class="title-row"><div><h1 id="project-detail-title">{{ project.name }}</h1><p class="status">{{ statusLabels[project.status] }}</p></div><section v-if="canShowMutations" data-project-mutations class="mutations" aria-label="项目维护操作"><ProjectEditForm v-if="project.capabilities.can_edit_project || project.capabilities.can_update_progress" :project="project" @updated="replaceProject" @reload="load" /><ProjectStatusForm v-if="project.capabilities.can_transition" :project="project" @updated="replaceProject" @reload="load" /><ProjectCorrectionDialog v-if="project.capabilities.can_correct_status" :project="project" mode="status" @updated="replaceProject" @reload="load" /><ProjectCorrectionDialog v-if="project.capabilities.can_correct_primary_entity" :project="project" mode="primary-entity" @updated="replaceProject" @reload="load" /></section></div></header>
      <section class="facts" aria-label="项目事实">
        <div><h2>关联政策</h2><p><RouterLink :to="`/policies/${project.policy.id}`">{{ project.policy.title }}</RouterLink></p><small>结论：{{ conclusionLabels[project.policy.conclusion] ?? project.policy.conclusion }}</small></div>
        <div><h2>主申报企业</h2><p>{{ project.primary_entity_legal_name }}</p><small>{{ project.primary_entity_seed_code }}</small></div>
        <div><h2>项目人员</h2><p>负责人：{{ project.applicant_owner.display_name }}</p><p>对接人：{{ project.liaison.display_name }}</p><small>成员：{{ project.members.map((member) => member.display_name).join("、") || "——" }}</small></div>
        <div><h2>关键日期</h2><p>截止：{{ display(project.dates.deadline_on) }}</p><p>提交：{{ display(project.dates.submitted_on) }}</p><p>结果：{{ display(project.dates.result_on) }}</p></div>
        <div><h2>记录</h2><p>进展：{{ display(project.notes.progress_note) }}</p><p>结果：{{ display(project.notes.result_note) }}</p><p>终止：{{ display(project.notes.termination_note) }}</p></div>
      </section>
      <ProjectStatusHistory :entries="project.status_history" />
    </template>
  </section>
</template>

<style scoped>
.project-detail{max-width:78rem;margin:0 auto;color:#29435f}.heading{margin-bottom:1rem;padding-bottom:1rem;border-bottom:2px solid #1e568c}.eyebrow{margin:0 0 .35rem;color:#6a7e95;font-size:.75rem;font-weight:800;letter-spacing:.1em}.title-row{display:flex;gap:1rem;justify-content:space-between;align-items:start}.heading h1{margin:0;color:#1b3352;font:700 clamp(1.75rem,3vw,2.4rem)/1.2 "Noto Serif SC","Songti SC",serif}.status{display:inline-block;margin:.65rem 0 0;padding:.2rem .5rem;color:#174f7e;background:#eef5fa;font-weight:800}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.facts>div,.mutations{padding:.85rem;border:1px solid #d8e2ec;background:#fff}.facts h2{margin:0 0 .5rem;color:#1b3352;font:700 1rem/1.2 "Noto Serif SC","Songti SC",serif}.facts p{margin:.35rem 0}.facts small{color:#60758d}.facts a{color:#174f7e;font-weight:700}.mutations{width:min(31rem,52vw);display:grid;gap:1rem}.error{padding:.75rem;color:#9b1c1c;background:#fff1f0}.error button{margin-left:.5rem}@media(max-width:720px){.facts{grid-template-columns:1fr}.title-row{display:block}.mutations{width:auto}}
</style>
