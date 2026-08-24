<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import { createSource, disableSource, enableSource, getSources, retrySourceRecognition, type PolicySource, type SourceCreateInput } from "../api/sources";
import { currentUser } from "../auth/state";
import { getBusinessErrorCode } from "../api/errors";
import SourceDrawer from "../components/sources/SourceDrawer.vue";
import SourceStatusCard from "../components/sources/SourceStatusCard.vue";

const pageSize = 20;
const mediaQuery = window.matchMedia("(max-width: 720px)");
const mobile = ref(mediaQuery.matches);
const sources = ref<PolicySource[]>([]);
const page = ref(1);
const total = ref(0);
const loading = ref(true);
const loadError = ref("");
const actionError = ref("");
const drawerOpen = ref(false);
const saving = ref(false);
const saveError = ref("");
const busySourceIds = ref(new Set<number>());

const canWrite = computed(() => !mobile.value && currentUser.value?.roles.includes("applicant_owner") === true);
const hasSources = computed(() => sources.value.length > 0);
const hasPreviousPage = computed(() => page.value > 1);
const hasNextPage = computed(() => page.value * pageSize < total.value);

function updateMobile(event: MediaQueryListEvent) { mobile.value = event.matches; }
function replaceSource(source: PolicySource) { sources.value = sources.value.map((item) => item.id === source.id ? source : item); }
function conflictMessage(error: unknown) {
  return responseStatus(error) === 409 || getBusinessErrorCode(error)?.code === "source_version_conflict"
    ? "来源已被更新，请重新加载后再操作。"
    : "操作未完成，请稍后重试。";
}
function responseStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object" || !("response" in error)) return undefined;
  const response = error.response;
  return response && typeof response === "object" && "status" in response && typeof response.status === "number" ? response.status : undefined;
}

async function loadSources(nextPage = page.value) {
  loading.value = true;
  loadError.value = "";
  try {
    const result = await getSources(nextPage, pageSize);
    sources.value = result.items;
    page.value = result.page;
    total.value = result.total;
  } catch {
    loadError.value = "无法加载政策来源。请检查网络后重试。";
  } finally {
    loading.value = false;
  }
}

function startCreate() { saveError.value = ""; drawerOpen.value = true; }
async function saveSource(payload: SourceCreateInput) {
  if (!canWrite.value || saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    await createSource(payload);
    drawerOpen.value = false;
    await loadSources(1);
  } catch (error) {
    saveError.value = responseStatus(error) === 422 ? "来源名称、公开入口或标签不符合要求。" : "无法提交来源。请稍后重试。";
  } finally {
    saving.value = false;
  }
}

function setBusy(id: number, busy: boolean) {
  const next = new Set(busySourceIds.value);
  if (busy) next.add(id); else next.delete(id);
  busySourceIds.value = next;
}
async function retry(id: number) {
  if (!canWrite.value || busySourceIds.value.has(id)) return;
  actionError.value = ""; setBusy(id, true);
  try { await retrySourceRecognition(id); await loadSources(page.value); } catch (error) { actionError.value = conflictMessage(error); } finally { setBusy(id, false); }
}
async function enable(id: number, version: number) {
  if (!canWrite.value || busySourceIds.value.has(id)) return;
  actionError.value = ""; setBusy(id, true);
  try { replaceSource(await enableSource(id, version)); } catch (error) { actionError.value = conflictMessage(error); } finally { setBusy(id, false); }
}
async function disable(id: number, version: number) {
  if (!canWrite.value || busySourceIds.value.has(id)) return;
  actionError.value = ""; setBusy(id, true);
  try { replaceSource(await disableSource(id, version)); } catch (error) { actionError.value = conflictMessage(error); } finally { setBusy(id, false); }
}

onMounted(() => { mediaQuery.addEventListener("change", updateMobile); void loadSources(); });
onUnmounted(() => mediaQuery.removeEventListener("change", updateMobile));
</script>

<template>
  <section class="sources-page" aria-labelledby="sources-title">
    <header class="page-heading">
      <div><p class="eyebrow">来源识别 · 安全预览 · 显式确认</p><h1 id="sources-title">政策来源</h1><p>提交公开入口后先查看识别结果与安全预览，再明确启用或停用采集。</p></div>
      <button v-if="canWrite" class="primary-action" type="button" aria-label="添加政策来源" @click="startCreate">添加来源</button>
    </header>

    <p v-if="loading" class="status-message" role="status">正在加载政策来源…</p>
    <section v-else-if="loadError" class="status-message status-message--error" role="alert"><p>{{ loadError }}</p><button type="button" aria-label="重新加载来源" @click="loadSources()">重新加载</button></section>
    <section v-else-if="!hasSources" class="empty-state" data-testid="empty-sources"><h2>还没有政策来源</h2><p>添加一个公开入口，先识别和预览，再决定是否启用采集。</p><button v-if="canWrite" class="primary-action" type="button" aria-label="添加政策来源" @click="startCreate">添加来源</button></section>
    <template v-else>
      <p v-if="actionError" class="action-error" role="alert">{{ actionError }} <button type="button" @click="loadSources()">重新加载</button></p>
      <div class="source-list"><SourceStatusCard v-for="source in sources" :key="source.id" :source="source" :can-write="canWrite" :busy="busySourceIds.has(source.id)" @retry="retry" @enable="enable" @disable="disable" /></div>
      <nav v-if="hasPreviousPage || hasNextPage" class="source-pages" aria-label="来源分页"><button v-if="hasPreviousPage" type="button" aria-label="上一页来源" @click="loadSources(page - 1)">上一页</button><span>第 {{ page }} 页</span><button v-if="hasNextPage" type="button" aria-label="下一页来源" @click="loadSources(page + 1)">下一页</button></nav>
    </template>
    <SourceDrawer v-if="canWrite" :open="drawerOpen" :saving="saving" :error="saveError" @close="drawerOpen = false" @save="saveSource" />
  </section>
</template>

<style scoped>
.sources-page { max-width: 68rem; margin: 0 auto; color: #1b3352; }.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 1.5rem; margin-bottom: 1.75rem; padding-bottom: 1.15rem; border-bottom: 2px solid #1e568c; }.eyebrow { margin: 0 0 .4rem; color: #6a7e95; font-size: .76rem; font-weight: 800; letter-spacing: .09em; }.page-heading h1, .empty-state h2 { margin: 0 0 .55rem; font-family: "Noto Serif SC", "Songti SC", serif; }.page-heading h1 { font-size: clamp(1.75rem, 3vw, 2.45rem); }.page-heading p:last-child { max-width: 48rem; margin: 0; color: #526a86; line-height: 1.65; }.primary-action, .status-message button, .action-error button, .source-pages button { min-height: 2.35rem; padding: .45rem .75rem; color: #1e568c; border: 1px solid #9db5cd; border-radius: .2rem; background: #fff; cursor: pointer; }.primary-action { color: #fff; border-color: #113a70; background: #113a70; }.primary-action:focus-visible, button:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }.status-message, .empty-state, .action-error { padding: 1.15rem; border: 1px solid #d6e1ec; background: #fff; }.status-message--error, .action-error { color: #9b1c1c; border-color: #f1b8b5; background: #fff1f0; }.status-message p { margin-top: 0; }.action-error { display: flex; align-items: center; justify-content: space-between; gap: .75rem; margin: 0 0 1rem; }.empty-state { border-top: 4px solid #d4a449; }.source-list { display: grid; gap: .8rem; }.source-pages { display: flex; align-items: center; justify-content: center; gap: .7rem; margin-top: 1.25rem; color: #526a86; font-size: .86rem; } @media (max-width: 720px) { .page-heading { align-items: start; flex-direction: column; }.primary-action { width: 100%; } } @media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; } }
</style>
