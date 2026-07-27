<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getPolicies, getPolicySourceOptions, type PolicyListItem, type SourceOption } from "../api/policies";
import ConclusionBadge from "../components/policies/ConclusionBadge.vue";

const route = useRoute();
const router = useRouter();
const rows = ref<PolicyListItem[]>([]);
const sources = ref<SourceOption[]>([]);
const total = ref(0);
const loading = ref(true);
const error = ref("");
const filters = reactive({
  q: typeof route.query.q === "string" ? route.query.q : "",
  source_id: typeof route.query.source_id === "string" ? route.query.source_id : "",
  published_from: typeof route.query.published_from === "string" ? route.query.published_from : "",
  published_to: typeof route.query.published_to === "string" ? route.query.published_to : "",
  page: Number(route.query.page ?? 1),
});

function query() {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== "" && value !== 1));
}
async function load() {
  loading.value = true; error.value = "";
  try {
    const result = await getPolicies({
      q: filters.q || undefined,
      source_id: filters.source_id ? Number(filters.source_id) : undefined,
      published_from: filters.published_from || undefined,
      published_to: filters.published_to || undefined,
      page: filters.page,
      page_size: 20,
    });
    rows.value = result.items; total.value = result.total;
  } catch { error.value = "无法加载政策列表。请检查网络后重试。"; }
  finally { loading.value = false; }
}
async function applyFilters() {
  filters.page = 1;
  await router.replace({ query: query() });
  await load();
}
async function changePage(page: number) {
  filters.page = page;
  await router.replace({ query: query() });
  await load();
}
onMounted(async () => {
  try { sources.value = await getPolicySourceOptions(); } catch { /* list remains usable */ }
  await load();
});
</script>

<template>
  <section class="policy-center" aria-labelledby="policy-center-title">
    <header class="page-heading">
      <p class="eyebrow">政策档案 · 可追溯原文</p>
      <h1 id="policy-center-title">政策中心</h1>
      <p>按名称、文号、来源和发布日期定位政策。</p>
    </header>
    <form class="filter-strip" @submit.prevent="applyFilters">
      <label>关键词<input v-model="filters.q" aria-label="搜索政策" placeholder="名称或文号" /></label>
      <label>来源<select v-model="filters.source_id"><option value="">全部来源</option><option v-for="source in sources" :key="source.id" :value="String(source.id)">{{ source.name }}</option></select></label>
      <label>发布起始<input v-model="filters.published_from" type="date" /></label>
      <label>发布截止<input v-model="filters.published_to" type="date" /></label>
      <button type="submit">筛选</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="loading" role="status">正在加载政策…</p>
    <div v-else class="table-frame">
      <el-table :data="rows" empty-text="没有符合条件的政策。" row-key="id">
        <el-table-column label="政策名称" min-width="320">
          <template #default="scope"><div class="policy-name"><RouterLink :to="`/policies/${scope.row.id}`">{{ scope.row.title }}</RouterLink><small v-if="scope.row.document_number">{{ scope.row.document_number }}</small></div></template>
        </el-table-column>
        <el-table-column label="发布日期" width="130"><template #default="scope">{{ scope.row.published_on ?? "日期未知" }}</template></el-table-column>
        <el-table-column label="申报截止日期" width="150"><template #default="scope">{{ scope.row.deadline_on ?? "未注明" }}</template></el-table-column>
        <el-table-column label="来源" min-width="190"><template #default="scope">{{ scope.row.sources.join("、") || "来源待核" }}</template></el-table-column>
        <el-table-column label="当前结论" width="140"><template #default="scope"><ConclusionBadge :conclusion="scope.row.current_conclusion" :confirmed="scope.row.conclusion_confirmed" /></template></el-table-column>
      </el-table>
    </div>
    <el-pagination v-if="total > 20" layout="prev, pager, next" :total="total" :page-size="20" :current-page="filters.page" @current-change="changePage" />
  </section>
</template>

<style scoped>
.policy-center { max-width: 82rem; margin: 0 auto; color: #1b3352; }.page-heading { margin-bottom: 1.25rem; padding-bottom: 1rem; border-bottom: 2px solid #1e568c; }.eyebrow { margin: 0 0 .35rem; color: #6a7e95; font-size: .75rem; font-weight: 800; letter-spacing: .1em; }.page-heading h1 { margin: 0; font: 700 clamp(1.75rem, 3vw, 2.4rem)/1.2 "Noto Serif SC", "Songti SC", serif; }.page-heading p:last-child { margin: .45rem 0 0; color: #58708a; }.filter-strip { display: grid; grid-template-columns: minmax(12rem, 2fr) minmax(10rem, 1fr) repeat(2, minmax(9rem, 1fr)) auto; gap: .75rem; align-items: end; margin-bottom: 1rem; padding: .9rem; border: 1px solid #d8e2ec; background: #fff; }.filter-strip label { display: grid; gap: .3rem; color: #5c7188; font-size: .75rem; font-weight: 700; }.filter-strip input, .filter-strip select { min-height: 2.35rem; padding: .35rem .55rem; border: 1px solid #aebfd0; background: #fff; }.filter-strip button { min-height: 2.35rem; padding: 0 1rem; color: #fff; border: 1px solid #113a70; background: #113a70; }.table-frame { overflow-x: auto; border: 1px solid #d8e2ec; background: #fff; }.table-frame :deep(.el-table) { min-width: 60rem; color: #293f58; }.table-frame :deep(.el-table__header th) { color: #526a86; background: #edf4f9; font-size: .78rem; }.policy-name a { color: #163f70; text-decoration-thickness: 1px; text-underline-offset: 3px; }.policy-name small { display: block; margin-top: .3rem; color: #75889b; }.error { padding: .8rem; color: #9b1c1c; background: #fff1f0; }@media (max-width: 900px) { .filter-strip { grid-template-columns: 1fr 1fr; }.filter-strip button { grid-column: 1 / -1; } }
</style>
