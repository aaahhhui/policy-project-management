<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter, useRoute } from "vue-router";

import { getProjectSummary, getProjects, type ProjectListItem, type ProjectSummary } from "../api/projects";
import { currentUser } from "../auth/state";
import ProjectCreateDrawer from "../components/projects/ProjectCreateDrawer.vue";
import ProjectFilters from "../components/projects/ProjectFilters.vue";
import { filtersFromQuery, filtersToQuery, type ProjectLedgerFilters } from "../components/projects/projectFilters";

const route = useRoute();
const router = useRouter();
const filters = ref<ProjectLedgerFilters>(filtersFromQuery(route.query));
const projects = ref<ProjectListItem[]>([]);
const total = ref(0);
const summary = ref<ProjectSummary | null>(null);
const summaryError = ref("");
const summaryLoading = ref(false);
const loading = ref(true);
const error = ref("");
const createOpen = ref(false);
const isMobile = ref(false);
const canCreate = computed(() => currentUser.value?.roles.includes("applicant_owner") ?? false);
const canConvert = computed(() => canCreate.value && !isMobile.value);
const conversionLabel = computed(() => summary.value ? `${summary.value.convertible_policy_count} 条政策可转项目` : "将政策转为项目");
const hasActiveFilters = computed(() => Boolean(
  filters.value.q.trim() || filters.value.primary_entity_seed_code.trim() || filters.value.liaison_id
  || filters.value.status || filters.value.deadline_from || filters.value.deadline_to || filters.value.mine,
));
let requestGeneration = 0;
let isActive = true;

const statusLabels: Record<string, string> = { pending_application: "待申报", submitted: "已提交", succeeded: "已成功", rejected: "未获批", terminated: "已终止" };
const statusOrder = ["pending_application", "submitted", "succeeded", "rejected", "terminated"];

function apiFilters(value: ProjectLedgerFilters) {
  const liaisonId = Number(value.liaison_id);
  return { q: value.q.trim() || undefined, primary_entity_seed_code: value.primary_entity_seed_code.trim() || undefined, liaison_user_id: Number.isInteger(liaisonId) && liaisonId > 0 ? liaisonId : undefined, status: value.status || undefined, deadline_from: value.deadline_from || undefined, deadline_to: value.deadline_to || undefined, mine: value.mine || undefined, page: value.page, page_size: value.page_size };
}
async function loadProjects(): Promise<void> {
  if (!isActive) return;
  const generation = ++requestGeneration;
  loading.value = true; error.value = "";
  try {
    const page = await getProjects(apiFilters(filters.value));
    if (isActive && generation === requestGeneration) {
      projects.value = page.items; total.value = page.total; filters.value.page = page.page;
      filters.value.page_size = [10, 20, 50].includes(page.page_size) ? page.page_size as 10 | 20 | 50 : 20;
      await canonicalizeRoute();
    }
  } catch {
    if (isActive && generation === requestGeneration) error.value = "无法加载项目台账，请检查网络后重试。";
  } finally { if (isActive && generation === requestGeneration) loading.value = false; }
}
async function loadSummary(): Promise<void> {
  summaryLoading.value = true; summaryError.value = "";
  try { summary.value = await getProjectSummary(); } catch { summary.value = null; summaryError.value = "无法加载项目汇总，请稍后重试。"; }
  finally { summaryLoading.value = false; }
}
async function replaceQuery(): Promise<void> { await router.replace({ query: filtersToQuery(filters.value) }); }
function queryIsCanonical(query: Record<string, unknown>, canonical: Record<string, string>): boolean {
  const queryKeys = Object.keys(query);
  const canonicalKeys = Object.keys(canonical);
  return queryKeys.length === canonicalKeys.length
    && canonicalKeys.every((key) => typeof query[key] === "string" && query[key] === canonical[key]);
}
async function canonicalizeRoute(): Promise<void> {
  if (isActive && !queryIsCanonical(route.query as Record<string, unknown>, filtersToQuery(filters.value))) await replaceQuery();
}
async function applyFilters(next: ProjectLedgerFilters): Promise<void> { filters.value = next; await replaceQuery(); await loadProjects(); }
async function changePage(page: number): Promise<void> { if (page < 1 || page === filters.value.page) return; filters.value = { ...filters.value, page }; await replaceQuery(); await loadProjects(); }
function formatDate(value: string | null): string { return value ?? "未注明"; }
function formatTime(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date); }
async function projectCreated(id: number): Promise<void> { createOpen.value = false; await router.push(`/projects/${id}`); }
function syncViewport(): void { isMobile.value = window.innerWidth <= 720; if (isMobile.value) createOpen.value = false; }
watch(() => route.query, async (query) => {
  filters.value = filtersFromQuery(query as Record<string, unknown>);
  await canonicalizeRoute();
  if (!isActive) return;
  await loadProjects();
}, { deep: true, immediate: true });
onMounted(() => { syncViewport(); window.addEventListener("resize", syncViewport); void loadSummary(); });
onBeforeUnmount(() => { isActive = false; requestGeneration += 1; window.removeEventListener("resize", syncViewport); });
</script>

<template>
  <section class="project-ledger" aria-labelledby="project-ledger-title">
    <header class="page-heading"><div><p class="eyebrow">项目管理 · 可追溯台账</p><h1 id="project-ledger-title">项目台账</h1><p>集中查看政策转化后的项目进展与申报信息。</p></div></header>
    <p v-if="summaryLoading" role="status">正在加载项目汇总…</p>
    <p v-else-if="summaryError" class="summary-error" role="alert">{{ summaryError }} <button type="button" data-retry-project-summary aria-label="重试加载项目汇总" @click="loadSummary">重试</button></p>
    <section v-else-if="summary" class="project-summary" aria-label="项目汇总"><p>共 {{ summary.total }} 个项目</p><ul><li v-for="status in statusOrder" :key="status">{{ statusLabels[status] }} {{ summary.by_status[status] ?? 0 }}</li></ul></section>
    <button v-if="canConvert" type="button" class="conversion-link" data-open-project-conversion @click="createOpen = true">{{ conversionLabel }}</button>
    <ProjectFilters :filters="filters" @apply="applyFilters" />
    <p v-if="loading" role="status">正在加载项目台账…</p>
    <template v-else>
      <p v-if="error" class="error" role="alert">{{ error }} <button type="button" data-retry-projects @click="loadProjects">重试</button></p>
      <div v-else-if="!projects.length" class="empty" role="status">{{ hasActiveFilters ? "没有符合条件的项目。" : "暂无项目。" }}</div>
      <div v-else class="table-frame"><table><thead><tr><th scope="col">项目 / 政策</th><th scope="col">主申报企业</th><th scope="col">对接人</th><th scope="col">状态</th><th scope="col">截止日期</th><th scope="col">更新时间</th></tr></thead><tbody><tr v-for="project in projects" :key="project.id"><td><RouterLink :to="`/projects/${project.id}`">{{ project.name }}</RouterLink><small>{{ project.policy_title }}</small></td><td>{{ project.primary_entity_legal_name }}<small>{{ project.primary_entity_seed_code }}</small></td><td>{{ project.liaison.display_name }}</td><td>{{ statusLabels[project.status] }}</td><td>{{ formatDate(project.deadline_on) }}</td><td>{{ formatTime(project.updated_at) }}</td></tr></tbody></table></div>
      <nav v-if="total > filters.page_size" class="pagination" aria-label="项目分页"><button type="button" aria-label="上一页" :disabled="filters.page === 1" @click="changePage(filters.page - 1)">上一页</button><span>第 {{ filters.page }} 页，共 {{ Math.ceil(total / filters.page_size) }} 页</span><button type="button" aria-label="下一页" :disabled="filters.page * filters.page_size >= total" @click="changePage(filters.page + 1)">下一页</button></nav>
    </template>
    <ProjectCreateDrawer v-if="canConvert" :open="createOpen" @close="createOpen = false" @created="projectCreated" />
  </section>
</template>

<style scoped>
.project-ledger{max-width:82rem;margin:0 auto;color:#1b3352}.page-heading{margin-bottom:1rem;padding-bottom:1rem;border-bottom:2px solid #1e568c}.eyebrow{margin:0 0 .35rem;color:#6a7e95;font-size:.75rem;font-weight:800;letter-spacing:.1em}.page-heading h1{margin:0;font:700 clamp(1.75rem,3vw,2.4rem)/1.2 "Noto Serif SC","Songti SC",serif}.page-heading p:last-child{margin:.45rem 0 0;color:#58708a}.project-summary{display:flex;align-items:center;flex-wrap:wrap;gap:.7rem;margin:0 0 1rem;padding:.7rem .85rem;color:#315671;background:#eef5fa;font-size:.86rem;font-weight:800}.project-summary p,.project-summary ul{margin:0}.project-summary ul{display:flex;flex-wrap:wrap;gap:.6rem;padding:0;list-style:none;font-weight:500}.conversion-link,.pagination button,.error button,.summary-error button{min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:800;cursor:pointer}.conversion-link{min-height:auto;margin-left:auto;padding:.2rem 0;color:#174f7e;border:0;background:transparent;text-decoration:underline;text-underline-offset:3px}.table-frame{overflow-x:auto;margin-top:1rem;border:1px solid #d8e2ec;background:#fff}table{width:100%;min-width:66rem;border-collapse:collapse}th,td{padding:.85rem .75rem;text-align:left;border-bottom:1px solid #e1e9f1}th{color:#526a86;background:#edf4f9;font-size:.78rem}td{color:#293f58;font-size:.9rem}td a{color:#163f70;font-weight:800;text-decoration-thickness:1px;text-underline-offset:3px}small{display:block;margin-top:.3rem;color:#75889b;font-size:.78rem}.error,.summary-error{margin-top:1rem;padding:.8rem;color:#9b1c1c;background:#fff1f0}.error button,.summary-error button{min-height:auto;margin-left:.5rem;padding:.25rem .55rem;color:#8a1c1c;border-color:#d69a98;background:#fff}.empty{margin-top:1rem;padding:2rem 1rem;color:#60758d;text-align:center;border:1px solid #d8e2ec;background:#fff}.pagination{display:flex;justify-content:end;align-items:center;gap:.7rem;margin-top:1rem}.pagination button:disabled{cursor:not-allowed;opacity:.55}button:focus-visible{outline:3px solid #e3b260;outline-offset:2px}@media(max-width:720px){.project-summary{align-items:start;flex-direction:column}.conversion-link{margin-left:0}}
</style>
