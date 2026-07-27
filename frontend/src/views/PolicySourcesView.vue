<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import { collectSource, getCollectionTask, type CollectionTask, type CollectionStatus } from "../api/collection";

import {
  createSource,
  getSources,
  toggleSource,
  updateSource,
  type PolicySource,
  type SourceCreateInput,
  type SourceUpdateInput,
} from "../api/sources";
import SourceDrawer from "../components/sources/SourceDrawer.vue";

const sources = ref<PolicySource[]>([]);
const loading = ref(true);
const loadError = ref("");
const drawerOpen = ref(false);
const editingSource = ref<PolicySource | null>(null);
const saving = ref(false);
const saveError = ref("");
const actionError = ref("");
const togglingSourceIds = ref(new Set<number>());
const collectingSourceIds = ref(new Set<number>());
const tasksBySource = ref(new Map<number, CollectionTask>());
const pollTimers = new Set<ReturnType<typeof setTimeout>>();

const hasSources = computed(() => sources.value.length > 0);

function adapterLabel(source: PolicySource) {
  return source.adapter_status === "ready" ? "已适配" : "待适配";
}

function formatTime(value: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "尚无记录";
}

function resultLabel(status: CollectionStatus | string | null) {
  return ({ pending: "等待采集", running: "采集中", succeeded: "成功", partial_failed: "部分失败", failed: "失败" } as Record<string, string>)[status ?? ""] ?? "尚无结果";
}

function isTerminal(status: CollectionStatus) {
  return ["succeeded", "partial_failed", "failed"].includes(status);
}

function schedulePoll(sourceId: number, taskId: number) {
  const timer = setTimeout(() => {
    pollTimers.delete(timer);
    void pollTask(sourceId, taskId);
  }, 3000);
  pollTimers.add(timer);
}

async function pollTask(sourceId: number, taskId: number) {
  try {
    const task = await getCollectionTask(taskId);
    tasksBySource.value = new Map(tasksBySource.value).set(sourceId, task);
    if (!isTerminal(task.status)) schedulePoll(sourceId, taskId);
  } catch {
    actionError.value = `无法刷新采集任务 #${taskId}。`;
  }
}

async function collect(source: PolicySource) {
  if (collectingSourceIds.value.has(source.id)) return;
  actionError.value = "";
  collectingSourceIds.value = new Set(collectingSourceIds.value).add(source.id);
  try {
    const task = await collectSource(source.id);
    tasksBySource.value = new Map(tasksBySource.value).set(source.id, task);
    if (!isTerminal(task.status)) schedulePoll(source.id, task.id);
  } catch {
    actionError.value = `无法启动“${source.name}”采集。请重试。`;
  } finally {
    const pending = new Set(collectingSourceIds.value);
    pending.delete(source.id);
    collectingSourceIds.value = pending;
  }
}

async function loadSources() {
  loading.value = true;
  loadError.value = "";
  try {
    sources.value = await getSources();
  } catch {
    loadError.value = "无法加载政策来源。请检查网络后重试。";
  } finally {
    loading.value = false;
  }
}

function startCreate() {
  saveError.value = "";
  editingSource.value = null;
  drawerOpen.value = true;
}

function startEdit(source: PolicySource) {
  saveError.value = "";
  editingSource.value = source;
  drawerOpen.value = true;
}

function responseStatus(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("response" in error)) return undefined;
  const response = error.response;
  if (typeof response !== "object" || response === null || !("status" in response)) return undefined;
  return typeof response.status === "number" ? response.status : undefined;
}

async function saveSource(payload: SourceCreateInput | SourceUpdateInput) {
  saving.value = true;
  saveError.value = "";
  try {
    if (editingSource.value) await updateSource(editingSource.value.id, payload);
    else {
      const { name, home_url, channels } = payload;
      await createSource({ name, home_url, channels });
    }
    drawerOpen.value = false;
    await loadSources();
  } catch (error) {
    const status = responseStatus(error);
    saveError.value = status === 409
      ? "该来源名称已存在。请使用其他名称。"
      : status === 422
        ? "名称、官网地址或栏目内容不符合要求。"
        : "无法保存来源。请稍后重试。";
  } finally {
    saving.value = false;
  }
}

async function toggle(source: PolicySource) {
  if (togglingSourceIds.value.has(source.id)) return;
  actionError.value = "";
  togglingSourceIds.value = new Set(togglingSourceIds.value).add(source.id);
  try {
    await toggleSource(source.id);
    await loadSources();
  } catch {
    actionError.value = "无法更新来源状态。请重试。";
  } finally {
    const pending = new Set(togglingSourceIds.value);
    pending.delete(source.id);
    togglingSourceIds.value = pending;
  }
}

onMounted(loadSources);
onUnmounted(() => {
  for (const timer of pollTimers) clearTimeout(timer);
  pollTimers.clear();
});
</script>

<template>
  <section class="sources-page" aria-labelledby="sources-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">来源目录 · 仅负责人可管理</p>
        <h1 id="sources-title">政策来源</h1>
        <p>维护政策网站和栏目。只有已适配且启用的来源才可进入采集流程。</p>
      </div>
      <button class="primary-action" type="button" aria-label="添加政策来源" @click="startCreate">添加来源</button>
    </header>

    <p v-if="loading" class="status-message" role="status">正在加载政策来源…</p>
    <section v-else-if="loadError" class="status-message status-message--error" role="alert">
      <p>{{ loadError }}</p>
      <button type="button" aria-label="重新加载来源" @click="loadSources">重新加载</button>
    </section>
    <section v-else-if="!hasSources" class="empty-state" data-testid="empty-sources">
      <h2>还没有政策来源</h2>
      <p>添加一个政策网站；新来源会以“待适配”状态保存，暂不能采集。</p>
      <button class="primary-action" type="button" @click="startCreate">添加来源</button>
    </section>
    <template v-else>
      <p v-if="actionError" class="action-error" role="alert">{{ actionError }}</p>
      <div class="source-table-wrap">
      <table>
        <thead><tr><th scope="col">来源名称</th><th scope="col">启用状态</th><th scope="col">适配状态</th><th scope="col">最近采集</th><th scope="col">最近结果</th><th scope="col">操作</th></tr></thead>
        <tbody>
          <tr v-for="source in sources" :key="source.id">
            <th scope="row"><span>{{ source.name }}</span><a :href="source.home_url" target="_blank" rel="noreferrer">官网</a></th>
            <td><span :class="['status-pill', source.is_enabled ? 'enabled' : 'disabled']">{{ source.is_enabled ? "启用" : "停用" }}</span></td>
            <td><span :class="['status-pill', source.adapter_status]">{{ adapterLabel(source) }}</span></td>
            <td>{{ formatTime(source.latest_collection_at) }}</td>
            <td>
              <span>{{ resultLabel(tasksBySource.get(source.id)?.status ?? source.latest_result) }}</span>
              <div v-if="tasksBySource.get(source.id)" class="task-detail">
                任务 #{{ tasksBySource.get(source.id)?.id }}
                <span v-if="tasksBySource.get(source.id)?.status === 'partial_failed'">
                  · 成功 {{ tasksBySource.get(source.id)?.succeeded_count }} / 失败 {{ tasksBySource.get(source.id)?.failed_count }}
                </span>
                <ul v-if="tasksBySource.get(source.id)?.items.some((item) => item.error_message)">
                  <li v-for="item in tasksBySource.get(source.id)?.items.filter((entry) => entry.error_message)" :key="item.id">{{ item.error_message }}</li>
                </ul>
              </div>
            </td>
            <td class="actions">
              <button type="button" :disabled="togglingSourceIds.has(source.id)" @click="startEdit(source)">编辑</button>
              <button type="button" :disabled="togglingSourceIds.has(source.id)" @click="toggle(source)">{{ source.is_enabled ? "停用" : "启用" }}</button>
              <button
                v-if="source.adapter_status === 'ready' && source.is_enabled"
                type="button"
                :aria-label="`立即采集 ${source.name}`"
                :disabled="collectingSourceIds.has(source.id) || ['pending', 'running'].includes(tasksBySource.get(source.id)?.status ?? '')"
                @click="collect(source)"
              >立即采集</button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </template>
    <SourceDrawer :open="drawerOpen" :source="editingSource" :saving="saving" :error="saveError" @close="drawerOpen = false" @save="saveSource" />
  </section>
</template>

<style scoped>
.sources-page { max-width: 78rem; margin: 0 auto; color: #1b3352; }.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 1.5rem; margin-bottom: 1.75rem; padding-bottom: 1.15rem; border-bottom: 2px solid #1e568c; }.eyebrow { margin: 0 0 .4rem; color: #6a7e95; font-size: .76rem; font-weight: 800; letter-spacing: .09em; }.page-heading h1, .empty-state h2 { margin: 0 0 .55rem; font-family: "Noto Serif SC", "Songti SC", serif; }.page-heading h1 { font-size: clamp(1.75rem, 3vw, 2.45rem); }.page-heading p:last-child { max-width: 48rem; margin: 0; color: #526a86; line-height: 1.65; }.primary-action, .actions button, .status-message button { min-height: 2.35rem; padding: .45rem .75rem; color: #1e568c; border: 1px solid #9db5cd; border-radius: .2rem; background: #fff; cursor: pointer; }.primary-action { color: #fff; border-color: #113a70; background: #113a70; }.primary-action:focus-visible, button:focus-visible, a:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }.status-message, .empty-state, .action-error { padding: 1.15rem; border: 1px solid #d6e1ec; background: #fff; }.status-message--error, .action-error { color: #9b1c1c; border-color: #f1b8b5; background: #fff1f0; }.status-message p { margin-top: 0; }.action-error { margin: 0 0 1rem; }.empty-state { border-top: 4px solid #d4a449; }.source-table-wrap { overflow-x: auto; border: 1px solid #d6e1ec; background: #fff; box-shadow: 0 .4rem 1rem rgb(25 58 94 / 6%); }table { width: 100%; min-width: 53rem; border-collapse: collapse; }th, td { padding: .9rem; border-bottom: 1px solid #e3ebf3; text-align: left; vertical-align: top; font-size: .9rem; }thead { color: #526a86; background: #eef5fa; }tbody th { display: grid; gap: .35rem; min-width: 12rem; color: #1b3352; }tbody th a { color: #1e568c; font-size: .78rem; font-weight: 500; }.status-pill { display: inline-block; padding: .18rem .48rem; border-radius: 99px; font-size: .78rem; font-weight: 700; }.enabled, .ready { color: #17633c; background: #e8f6ed; }.disabled { color: #7f1d1d; background: #fff0ef; }.pending { color: #79530e; background: #fff8e9; }.actions { display: flex; flex-wrap: wrap; gap: .45rem; min-width: 9rem; }.actions button:disabled { cursor: not-allowed; color: #77899c; border-color: #c9d4de; background: #f3f6f8; }.task-detail { margin-top: .35rem; color: #526a86; font-size: .78rem; }.task-detail ul { margin: .35rem 0 0; padding-left: 1rem; color: #9b1c1c; }@media (max-width: 720px) { .page-heading { align-items: start; flex-direction: column; }.primary-action { width: 100%; }.source-table-wrap { margin-right: -1.25rem; margin-left: -1.25rem; } }
</style>
