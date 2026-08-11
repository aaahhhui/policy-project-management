<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import {
  getNotification, listNotifications, retryNotification,
  type NotificationDetail, type NotificationFilters, type NotificationListItem, type NotificationStatus,
} from "../api/notifications";

const filters = reactive({ event_type: "", status: "", from: "", to: "" });
const records = ref<NotificationListItem[]>([]);
const selected = ref<NotificationDetail | null>(null);
const page = ref(1);
const pageSize = ref<10 | 20 | 50>(20);
const total = ref(0);
const loading = ref(true);
const detailLoading = ref(false);
const retrying = ref(false);
const error = ref("");
const detailError = ref("");
const conflict = ref("");
const isMobile = ref(false);
let requestGeneration = 0;
let active = true;

const hasFilters = computed(() => Boolean(filters.event_type || filters.status || filters.from || filters.to));
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const snapshotEntries = computed(() => Object.entries(selected.value?.message_snapshot ?? {}));
const statusLabels: Record<NotificationStatus, string> = {
  pending: "等待发送", sending: "正在发送", retry_wait: "等待重试", succeeded: "发送成功", failed: "最终失败",
};
const triggerLabels: Record<string, string> = {
  initial: "首次发送", automatic_retry: "自动重试", manual_retry: "手动重发",
};
const resultLabels: Record<string, string> = {
  succeeded: "成功", retryable_failure: "可重试失败", permanent_failure: "永久失败", uncertain: "结果不确定",
};
const snapshotLabels: Record<string, string> = {
  primary_entity_legal_name: "主申报企业", liaison_display_name: "项目对接人", deadline_on: "截止日期",
  submitted_on: "提交日期", result_on: "结果日期", result_note: "结果说明",
  consecutive_failure_count: "连续失败次数", latest_task_id: "最近采集任务", failure_summary: "异常摘要",
  conclusion: "评估结论", previous_conclusion: "上次结论", high_match: "是否高匹配",
  high_match_score_threshold: "高匹配阈值", changed_fields: "变化字段",
};

function iso(value: string): string | undefined {
  if (!value) return undefined;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}
function requestFilters(): NotificationFilters {
  return {
    event_type: filters.event_type || undefined,
    status: (filters.status || undefined) as NotificationStatus | undefined,
    triggered_from: iso(filters.from), triggered_to: iso(filters.to), page: page.value, page_size: pageSize.value,
  };
}
async function loadRecords(): Promise<void> {
  const generation = ++requestGeneration;
  loading.value = true; error.value = "";
  try {
    const result = await listNotifications(requestFilters());
    if (!active || generation !== requestGeneration) return;
    records.value = result.items; page.value = result.page; total.value = result.total;
  } catch {
    if (active && generation === requestGeneration) error.value = "无法加载通知记录，请检查网络后重试。";
  } finally {
    if (active && generation === requestGeneration) loading.value = false;
  }
}
async function applyFilters(): Promise<void> { page.value = 1; selected.value = null; await loadRecords(); }
async function changePage(next: number): Promise<void> {
  if (next < 1 || next > totalPages.value || next === page.value) return;
  page.value = next; selected.value = null; await loadRecords();
}
async function openDetail(id: number): Promise<void> {
  detailLoading.value = true; detailError.value = ""; conflict.value = "";
  try { selected.value = await getNotification(id); }
  catch { detailError.value = "无法加载通知详情，请稍后重试。"; }
  finally { detailLoading.value = false; }
}
function errorCode(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const response = (value as { response?: { data?: { detail?: { code?: unknown } } } }).response;
  const code = response?.data?.detail?.code;
  return typeof code === "string" ? code : null;
}
async function retry(): Promise<void> {
  const current = selected.value;
  if (!current || current.status !== "failed" || isMobile.value) return;
  retrying.value = true; detailError.value = ""; conflict.value = "";
  try { selected.value = await retryNotification(current.id, current.version); await loadRecords(); }
  catch (requestError) {
    if (errorCode(requestError) === "notification_version_conflict") {
      await openDetail(current.id);
      conflict.value = "记录已被更新，已为你刷新当前详情。";
    } else detailError.value = "重新发送未启动，请稍后重试。";
  } finally { retrying.value = false; }
}
function formatTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}
function snapshotValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function snapshotLabel(key: string): string { return snapshotLabels[key] ?? key; }
function syncViewport(): void { isMobile.value = window.innerWidth <= 720; }
onMounted(() => { syncViewport(); window.addEventListener("resize", syncViewport); void loadRecords(); });
onBeforeUnmount(() => { active = false; requestGeneration += 1; window.removeEventListener("resize", syncViewport); });
</script>

<template>
  <section class="notification-ledger" aria-labelledby="notification-title">
    <header class="page-heading">
      <div><p class="eyebrow">通知闭环 · 投递可追溯</p><h1 id="notification-title">通知记录</h1><p>查看企业微信群消息的发送结果、失败原因与每次投递轨迹。</p></div>
      <p class="ledger-count"><strong>{{ total }}</strong><span>条记录</span></p>
    </header>
    <form class="filters" aria-label="通知记录筛选" @submit.prevent="applyFilters">
      <label>通知类型<select v-model="filters.event_type" data-filter-type><option value="">全部类型</option><option value="evaluation_material_change">评估结果变化</option><option value="project_created">政策转项目</option><option value="project_first_submitted">项目首次提交</option><option value="project_first_succeeded">项目首次成功</option><option value="source_failure_episode">来源连续异常</option></select></label>
      <label>发送状态<select v-model="filters.status" data-filter-status><option value="">全部状态</option><option v-for="(label, value) in statusLabels" :key="value" :value="value">{{ label }}</option></select></label>
      <label>开始时间<input v-model="filters.from" data-filter-from type="datetime-local" /></label>
      <label>结束时间<input v-model="filters.to" data-filter-to type="datetime-local" /></label>
      <button type="submit" data-apply-notification-filters>应用筛选</button>
    </form>
    <p v-if="loading" role="status">正在加载通知记录…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }} <button type="button" @click="loadRecords">重试</button></p>
    <div v-else-if="!records.length" class="empty" role="status">{{ hasFilters ? "当前筛选没有匹配记录。" : "尚无通知记录。业务事件触发后会在这里显示。" }}</div>
    <div v-else class="ledger-grid">
      <section class="records" aria-label="通知列表">
        <button v-for="record in records" :key="record.id" type="button" class="record-row" :class="{ selected: selected?.id === record.id }" :data-open-notification="record.id" @click="openDetail(record.id)">
          <span class="record-main"><strong>{{ record.display_type }}</strong><span>{{ record.object_name }}</span></span>
          <span class="record-meta"><time>{{ formatTime(record.triggered_at) }}</time><b :data-status="record.status">{{ statusLabels[record.status] }}</b></span>
          <span class="record-attempts">尝试 {{ record.attempt_count }} 次<span v-if="record.last_failure_summary">{{ record.last_failure_summary }}</span></span>
        </button>
        <nav class="pagination" aria-label="通知分页"><button type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button><span>第 {{ page }} / {{ totalPages }} 页</span><button type="button" data-next-notification-page :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button></nav>
      </section>
      <aside class="detail" aria-live="polite">
        <p v-if="detailLoading" role="status">正在加载投递详情…</p>
        <p v-else-if="detailError" class="error" role="alert">{{ detailError }}</p>
        <div v-else-if="selected">
          <header class="detail-heading"><div><p class="eyebrow">记录 #{{ selected.id }}</p><h2>{{ selected.display_type }}</h2><p>{{ selected.object_name }}</p></div><span class="status-chip" :data-status="selected.status">{{ statusLabels[selected.status] }}</span></header>
          <p v-if="conflict" class="conflict" data-notification-conflict role="status">{{ conflict }}</p>
          <dl class="snapshot"><div v-for="([key, value]) in snapshotEntries" :key="key"><dt>{{ snapshotLabel(key) }}</dt><dd>{{ snapshotValue(value) }}</dd></div></dl>
          <RouterLink class="object-link" :to="selected.detail_path">查看业务详情</RouterLink>
          <section class="attempt-history" aria-labelledby="attempt-title"><h3 id="attempt-title">发送轨迹</h3><ol><li v-for="attempt in selected.attempts" :key="attempt.id"><span class="track-dot" aria-hidden="true"></span><div><strong>第 {{ attempt.attempt_number }} 次 · {{ triggerLabels[attempt.trigger_type] ?? attempt.trigger_type }}</strong><time>{{ formatTime(attempt.started_at) }}</time><p>{{ attempt.result ? (resultLabels[attempt.result] ?? attempt.result) : "处理中" }}</p><small v-if="attempt.failure_summary">{{ attempt.failure_summary }}</small></div></li></ol></section>
          <button v-if="selected.status === 'failed' && !isMobile" type="button" class="retry-button" :data-retry-notification="selected.id" :disabled="retrying" @click="retry">{{ retrying ? "正在启动…" : "重新发送" }}</button>
        </div>
        <div v-else class="detail-empty"><span aria-hidden="true">↗</span><p>选择一条记录，查看安全消息快照与完整发送轨迹。</p></div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.notification-ledger{max-width:88rem;margin:0 auto;color:#1b3352}.page-heading{display:flex;align-items:end;justify-content:space-between;gap:2rem;margin-bottom:1rem;padding-bottom:1rem;border-bottom:2px solid #1e568c}.eyebrow{margin:0 0 .35rem;color:#687e96;font-size:.73rem;font-weight:800;letter-spacing:.11em}.page-heading h1,.detail-heading h2{margin:0;font:700 clamp(1.75rem,3vw,2.4rem)/1.2 "Noto Serif SC","Songti SC",serif}.page-heading p:last-child,.detail-heading p{margin:.45rem 0 0;color:#58708a}.ledger-count{display:flex;align-items:baseline;gap:.35rem;margin:0;color:#506983}.ledger-count strong{color:#174f7e;font:700 2.2rem/1 "Noto Serif SC","Songti SC",serif}.filters{display:grid;grid-template-columns:1.1fr 1fr 1.2fr 1.2fr auto;align-items:end;gap:.65rem;padding:.9rem;border:1px solid #d6e1ec;background:#eef5fa}.filters label{display:grid;gap:.32rem;color:#435d78;font-size:.75rem;font-weight:800}.filters select,.filters input{min-height:2.45rem;padding:.45rem .55rem;color:#223d5b;border:1px solid #b9cad9;background:#fff;font:inherit}.filters button,.pagination button,.retry-button,.error button{min-height:2.45rem;padding:.45rem .85rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:800;cursor:pointer}.ledger-grid{display:grid;grid-template-columns:minmax(28rem,1.2fr) minmax(21rem,.8fr);gap:1rem;margin-top:1rem}.records,.detail{border:1px solid #d8e2ec;background:#fff}.record-row{display:grid;grid-template-columns:1fr auto;gap:.45rem;width:100%;padding:1rem;border:0;border-bottom:1px solid #e2eaf1;background:#fff;color:inherit;text-align:left;cursor:pointer}.record-row:hover,.record-row.selected{background:#f0f6fa}.record-row.selected{box-shadow:4px 0 0 #d29c42 inset}.record-main,.record-meta,.record-attempts{display:flex}.record-main{flex-direction:column;gap:.22rem}.record-main strong{font-family:"Noto Serif SC","Songti SC",serif}.record-main span,.record-attempts,.record-meta time{color:#6a7e92;font-size:.78rem}.record-meta{align-items:end;flex-direction:column;gap:.35rem}.record-meta b,.status-chip{padding:.2rem .45rem;color:#315c79;background:#e8f1f7;font-size:.72rem}.record-meta b[data-status="failed"],.status-chip[data-status="failed"]{color:#8c2924;background:#fff0ee}.record-meta b[data-status="succeeded"],.status-chip[data-status="succeeded"]{color:#24603c;background:#edf7f0}.record-attempts{grid-column:1/-1;justify-content:space-between;gap:1rem}.record-attempts span{overflow:hidden;max-width:34rem;text-overflow:ellipsis;white-space:nowrap}.pagination{display:flex;align-items:center;justify-content:end;gap:.7rem;padding:.8rem}.pagination button:disabled,.retry-button:disabled{cursor:not-allowed;opacity:.5}.detail{min-height:25rem;padding:1.2rem}.detail-heading{display:flex;align-items:start;justify-content:space-between;gap:1rem;padding-bottom:1rem;border-bottom:1px solid #dce6ee}.detail-heading h2{font-size:1.35rem}.snapshot{margin:1rem 0}.snapshot div{display:grid;grid-template-columns:minmax(7rem,.65fr) 1.35fr;gap:.75rem;padding:.55rem 0;border-bottom:1px solid #edf1f5}.snapshot dt{color:#61768c;font-size:.78rem;font-weight:700;overflow-wrap:anywhere}.snapshot dd{margin:0;overflow-wrap:anywhere}.object-link{display:inline-block;color:#174f7e;font-weight:800;text-underline-offset:3px}.attempt-history{margin-top:1.4rem}.attempt-history h3{margin:0 0 .8rem;font:700 1rem/1.3 "Noto Serif SC","Songti SC",serif}.attempt-history ol{margin:0;padding:0;list-style:none}.attempt-history li{position:relative;display:grid;grid-template-columns:1rem 1fr;gap:.6rem;padding-bottom:1.1rem}.attempt-history li:not(:last-child)::before{position:absolute;top:.85rem;bottom:-.15rem;left:.34rem;width:1px;background:#bfd0dd;content:""}.track-dot{position:relative;z-index:1;width:.7rem;height:.7rem;margin-top:.2rem;border:2px solid #fff;border-radius:50%;background:#27729b;box-shadow:0 0 0 1px #27729b}.attempt-history strong,.attempt-history time{display:block}.attempt-history time,.attempt-history small{margin-top:.25rem;color:#6d8093;font-size:.76rem}.attempt-history p{margin:.25rem 0 0}.attempt-history small{display:block;color:#8a3d38}.retry-button{margin-top:.4rem;background:#174f7e}.conflict,.error{padding:.7rem;color:#8a3d38;background:#fff1ef}.empty,.detail-empty{display:grid;place-items:center;min-height:14rem;padding:2rem;color:#687d91;text-align:center;border:1px solid #d8e2ec;background:#fff}.detail-empty{min-height:22rem;border:0}.detail-empty span{color:#d29c42;font:400 3rem/1 Georgia,serif}.detail-empty p{max-width:16rem;line-height:1.7}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #e3b260;outline-offset:2px}@media(max-width:980px){.filters{grid-template-columns:1fr 1fr}.filters button{grid-column:1/-1}.ledger-grid{grid-template-columns:1fr}}@media(max-width:720px){.page-heading{align-items:start;flex-direction:column;gap:.8rem}.filters{grid-template-columns:1fr}.filters button{grid-column:auto}.ledger-grid{display:block}.detail{margin-top:1rem}.record-row{grid-template-columns:1fr}.record-meta{align-items:start}.record-attempts{grid-column:auto;flex-direction:column}.snapshot div{grid-template-columns:1fr}.retry-button{display:none}}
</style>
