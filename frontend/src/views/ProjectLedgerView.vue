<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";

import { getProjectSummary, getProjects, type ProjectListItem, type ProjectSummary } from "../api/projects";
import { currentUser } from "../auth/state";
import ProjectCreateDrawer from "../components/projects/ProjectCreateDrawer.vue";
import ProjectFilters, { filtersFromQuery, filtersToQuery, type ProjectLedgerFilters } from "../components/projects/ProjectFilters.vue";

const route = useRoute();
const router = useRouter();
const filters = ref<ProjectLedgerFilters>(filtersFromQuery(route.query));
const projects = ref<ProjectListItem[]>([]);
const total = ref(0);
const summary = ref<ProjectSummary | null>(null);
const loading = ref(true);
const error = ref("");
const createOpen = ref(false);
const canCreate = computed(() => currentUser.value?.roles.includes("applicant_owner") ?? false);
let requestGeneration = 0;

const statusLabels: Record<string, string> = { pending_application: "待申报", submitted: "已提交", succeeded: "已成功", rejected: "未获批", terminated: "已终止" };

function apiFilters(value: ProjectLedgerFilters) {
  const liaisonId = Number(value.liaison_id);
  return { q: value.q.trim() || undefined, primary_entity_seed_code: value.primary_entity_seed_code.trim() || undefined, liaison_user_id: Number.isInteger(liaisonId) && liaisonId > 0 ? liaisonId : undefined, status: value.status || undefined, deadline_from: value.deadline_from || undefined, deadline_to: value.deadline_to || undefined, mine: value.mine || undefined, page: value.page, page_size: value.page_size };
}
async function loadProjects(): Promise<void> {
  const generation = ++requestGeneration;
  loading.value = true; error.value = "";
  try {
    const page = await getProjects(apiFilters(filters.value));
    if (generation === requestGeneration) { projects.value = page.items; total.value = page.total; filters.value.page = page.page; filters.value.page_size = page.page_size; }
  } catch {
    if (generation === requestGeneration) error.value = "无法加载项目台账，请检查网络后重试。";
  } finally { if (generation === requestGeneration) loading.value = false; }
}
async function loadSummary(): Promise<void> { try { summary.value = await getProjectSummary(); } catch { summary.value = null; } }
async function replaceQuery(): Promise<void> { await router.replace({ query: filtersToQuery(filters.value) }); }
async function applyFilters(next: ProjectLedgerFilters): Promise<void> { filters.value = next; await replaceQuery(); await loadProjects(); }
async function changePage(page: number): Promise<void> { if (page < 1 || page === filters.value.page) return; filters.value = { ...filters.value, page }; await replaceQuery(); await loadProjects(); }
function formatDate(value: string | null): string { return value ?? "未注明"; }
function formatTime(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date); }
async function projectCreated(id: number): Promise<void> { createOpen.value = false; await router.push(`/projects/${id}`); }
onMounted(() => { void loadSummary(); void loadProjects(); });
</script>

<template>
  <section class="project-ledger" aria-labelledby="project-ledger-title">
    <header class="page-heading"><div><p class="eyebrow">项目管理 · 可追溯台账</p><h1 id="project-ledger-title">项目台账</h1><p>集中查看政策转化后的项目进展与申报信息。</p></div><button v-if="canCreate" type="button" data-open-project-conversion @click="createOpen = true">将政策转为项目</button></header>
    <p v-if="summary" class="summary-count">{{ summary.convertible_policy_count }} 条政策可转项目</p>
    <ProjectFilters :filters="filters" @apply="applyFilters" />
    <p v-if="loading" role="status">正在加载项目台账…</p>
    <template v-else>
      <p v-if="error" class="error" role="alert">{{ error }} <button type="button" data-retry-projects @click="loadProjects">重试</button></p>
      <div v-else-if="!projects.length" class="empty" role="status">没有符合条件的项目。</div>
      <div v-else class="table-frame"><table><thead><tr><th scope="col">项目 / 政策</th><th scope="col">主申报企业</th><th scope="col">对接人</th><th scope="col">状态</th><th scope="col">截止日期</th><th scope="col">更新时间</th></tr></thead><tbody><tr v-for="project in projects" :key="project.id"><td><RouterLink :to="`/projects/${project.id}`">{{ project.name }}</RouterLink><small>{{ project.policy_title }}</small></td><td>{{ project.primary_entity_legal_name }}<small>{{ project.primary_entity_seed_code }}</small></td><td>{{ project.liaison.display_name }}</td><td>{{ statusLabels[project.status] }}</td><td>{{ formatDate(project.deadline_on) }}</td><td>{{ formatTime(project.updated_at) }}</td></tr></tbody></table></div>
      <nav v-if="total > filters.page_size" class="pagination" aria-label="项目分页"><button type="button" aria-label="上一页" :disabled="filters.page === 1" @click="changePage(filters.page - 1)">上一页</button><span>第 {{ filters.page }} 页，共 {{ Math.ceil(total / filters.page_size) }} 页</span><button type="button" aria-label="下一页" :disabled="filters.page * filters.page_size >= total" @click="changePage(filters.page + 1)">下一页</button></nav>
    </template>
    <ProjectCreateDrawer :open="createOpen" @close="createOpen = false" @created="projectCreated" />
  </section>
</template>

<style scoped>
.project-ledger{max-width:82rem;margin:0 auto;color:#1b3352}.page-heading{display:flex;justify-content:space-between;align-items:end;gap:1rem;margin-bottom:1rem;padding-bottom:1rem;border-bottom:2px solid #1e568c}.eyebrow{margin:0 0 .35rem;color:#6a7e95;font-size:.75rem;font-weight:800;letter-spacing:.1em}.page-heading h1{margin:0;font:700 clamp(1.75rem,3vw,2.4rem)/1.2 "Noto Serif SC","Songti SC",serif}.page-heading p:last-child{margin:.45rem 0 0;color:#58708a}.page-heading button,.pagination button,.error button{min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:800;cursor:pointer}.summary-count{display:inline-block;margin:0 0 1rem;padding:.45rem .65rem;color:#315671;background:#eef5fa;font-size:.86rem;font-weight:800}.table-frame{overflow-x:auto;margin-top:1rem;border:1px solid #d8e2ec;background:#fff}table{width:100%;min-width:66rem;border-collapse:collapse}th,td{padding:.85rem .75rem;text-align:left;border-bottom:1px solid #e1e9f1}th{color:#526a86;background:#edf4f9;font-size:.78rem}td{color:#293f58;font-size:.9rem}td a{color:#163f70;font-weight:800;text-decoration-thickness:1px;text-underline-offset:3px}small{display:block;margin-top:.3rem;color:#75889b;font-size:.78rem}.error{margin-top:1rem;padding:.8rem;color:#9b1c1c;background:#fff1f0}.error button{min-height:auto;margin-left:.5rem;padding:.25rem .55rem;color:#8a1c1c;border-color:#d69a98;background:#fff}.empty{margin-top:1rem;padding:2rem 1rem;color:#60758d;text-align:center;border:1px solid #d8e2ec;background:#fff}.pagination{display:flex;justify-content:end;align-items:center;gap:.7rem;margin-top:1rem}.pagination button:disabled{cursor:not-allowed;opacity:.55}button:focus-visible{outline:3px solid #e3b260;outline-offset:2px}@media(max-width:700px){.page-heading{align-items:stretch;flex-direction:column}.page-heading [data-open-project-conversion]{display:none}}
</style>
