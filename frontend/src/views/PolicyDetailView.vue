<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import {
  createEvaluation,
  cancelEvaluation,
  getEvaluations,
  getPrimaryEntityHistory,
  type EvaluationBatch,
  type PrimaryEntityDecision,
} from "../api/evaluations";
import { useEvaluationPolling } from "../composables/useEvaluationPolling";
import { getPolicy, getPolicyVersions, type PolicyDetail, type PolicyVersion } from "../api/policies";
import { currentUser } from "../auth/state";
import EvaluationHistory from "../components/evaluations/EvaluationHistory.vue";
import EvaluationSummary from "../components/evaluations/EvaluationSummary.vue";
import EvaluationConfirmationForm from "../components/evaluations/EvaluationConfirmationForm.vue";
import PrimaryEntitySelector from "../components/evaluations/PrimaryEntitySelector.vue";
import AttachmentList from "../components/policies/AttachmentList.vue";
import ConclusionBadge from "../components/policies/ConclusionBadge.vue";
import VersionHistory from "../components/policies/VersionHistory.vue";

const route = useRoute();
const policy = ref<PolicyDetail | null>(null);
const versions = ref<PolicyVersion[]>([]);
const evaluations = ref<EvaluationBatch[]>([]);
const loading = ref(true);
const error = ref("");
const evaluationError = ref("");
const evaluationLoading = ref(true);
const primaryEntity = ref<PrimaryEntityDecision | null>(null);
const confirmRetryOpen = ref(false);
const retrying = ref(false);
const cancelOpen = ref(false);
const cancelling = ref(false);
const cancelReason = ref("");
const cancelButton = ref<HTMLButtonElement | null>(null);
const cancelDialog = ref<HTMLElement | null>(null);
const confirmCancelButton = ref<HTMLButtonElement | null>(null);
const retryButton = ref<HTMLButtonElement | null>(null);
const retryDialog = ref<HTMLElement | null>(null);
const confirmRetryButton = ref<HTMLButtonElement | null>(null);
const currentEvaluation = computed(() => evaluations.value[0] ?? null);
const historicalEvaluations = computed(() => evaluations.value.slice(1));
const attemptNumberById = computed<Record<number, number>>(() => Object.fromEntries(
  [...evaluations.value]
    .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at) || left.id - right.id)
    .map((evaluation, index) => [evaluation.id, index + 1]),
));
const canRetry = computed(
  () => currentUser.value?.roles.includes("applicant_owner") ?? false,
);
const isEvaluationActive = computed(
  () => currentEvaluation.value !== null && ["pending", "running"].includes(currentEvaluation.value.status),
);
function formatDate(value: string | null) { return value ?? "未注明"; }
function formatTime(value: string) { return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }

async function refreshEvaluations(id: number): Promise<boolean> {
  try {
    evaluations.value = await getEvaluations(id);
    evaluationError.value = "";
    return true;
  } catch {
    evaluationError.value = "评估记录暂时无法加载，请稍后刷新页面。";
    return false;
  } finally {
    evaluationLoading.value = false;
  }
}

async function refreshPrimaryEntity(id: number): Promise<void> {
  try {
    const history = await getPrimaryEntityHistory(id);
    primaryEntity.value = history.find((decision) => decision.is_current) ?? null;
  } catch {
    primaryEntity.value = null;
  }
}

async function confirmRetry(): Promise<void> {
  if (!policy.value || retrying.value) return;
  retrying.value = true;
  await nextTick();
  retryDialog.value?.focus();
  evaluationError.value = "";
  try {
    const created = await createEvaluation(policy.value.id);
    evaluations.value = [created, ...evaluations.value.filter((item) => item.id !== created.id)];
    confirmRetryOpen.value = false;
    if (!await refreshEvaluations(policy.value.id)) {
      evaluationError.value = "新的评估批次已创建，但历史记录暂时无法刷新。";
    }
  } catch {
    evaluationError.value = "无法创建新的评估批次，请稍后重试。";
  } finally {
    retrying.value = false;
  }
}

async function confirmCancellation(): Promise<void> {
  const evaluation = currentEvaluation.value;
  if (!policy.value || !evaluation || cancelling.value) return;
  cancelling.value = true;
  evaluationError.value = "";
  try {
    await cancelEvaluation(evaluation.id, cancelReason.value.trim() || null);
    cancelOpen.value = false;
    cancelReason.value = "";
    await refreshEvaluations(policy.value.id);
  } catch {
    evaluationError.value = "Unable to cancel this evaluation. Please try again.";
  } finally {
    cancelling.value = false;
  }
}

function dismissCancelDialog(): void {
  if (!cancelling.value) cancelOpen.value = false;
}

function dismissRetryDialog(): void {
  if (!retrying.value) confirmRetryOpen.value = false;
}

function handleDialogKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    dismissRetryDialog();
    return;
  }
  if (event.key !== "Tab" || !retryDialog.value) return;
  const buttons = Array.from(
    retryDialog.value.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
  );
  if (!buttons.length) {
    event.preventDefault();
    retryDialog.value.focus();
    return;
  }
  const first = buttons[0];
  const last = buttons[buttons.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function handleCancelDialogKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.preventDefault();
    dismissCancelDialog();
    return;
  }
  if (event.key !== "Tab" || !cancelDialog.value) return;
  const buttons = Array.from(
    cancelDialog.value.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
  );
  if (!buttons.length) {
    event.preventDefault();
    cancelDialog.value.focus();
    return;
  }
  const first = buttons[0];
  const last = buttons[buttons.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

watch(confirmRetryOpen, async (open) => {
  await nextTick();
  if (open) {
    confirmRetryButton.value?.focus();
  } else if (retryButton.value?.isConnected) {
    retryButton.value.focus();
  }
});

watch(cancelOpen, async (open) => {
  await nextTick();
  if (open) {
    confirmCancelButton.value?.focus();
  } else if (cancelButton.value?.isConnected) {
    cancelButton.value.focus();
  }
});

useEvaluationPolling(
  () => policy.value ? refreshEvaluations(policy.value.id) : Promise.resolve(),
  isEvaluationActive,
);

onMounted(async () => {
  const id = Number(route.params.id);
  try {
    [policy.value, versions.value] = await Promise.all([getPolicy(id), getPolicyVersions(id)]);
    void refreshEvaluations(id);
    void refreshPrimaryEntity(id);
  }
  catch { error.value = "无法加载政策详情。请返回政策中心后重试。"; }
  finally { loading.value = false; }
});
</script>

<template>
  <p v-if="loading" role="status">正在加载政策详情…</p>
  <p v-else-if="error" role="alert" class="error">{{ error }}</p>
  <article v-else-if="policy" class="policy-detail">
    <header class="policy-title">
      <div><p class="eyebrow">政策档案 · 当前版本 {{ policy.current_version.version_number }}</p><h1>{{ policy.title }}</h1><p v-if="policy.document_number">{{ policy.document_number }}</p></div>
      <ConclusionBadge :conclusion="policy.current_conclusion" :confirmed="policy.conclusion_confirmed" />
    </header>
    <section class="facts" aria-label="政策日期与来源">
      <dl><div><dt>发布日期</dt><dd>{{ formatDate(policy.published_on) }}</dd></div><div><dt>申报截止日期</dt><dd>{{ formatDate(policy.deadline_on) }}</dd></div><div><dt>采集时间</dt><dd>{{ formatTime(policy.current_version.collected_at) }}</dd></div></dl>
      <ul><li v-for="discovery in policy.discoveries" :key="discovery.id"><strong>{{ discovery.source_name }} · {{ discovery.channel_name }}</strong><a :href="discovery.original_url" target="_blank" rel="noreferrer">查看官方原文</a></li></ul>
    </section>
    <section class="document" aria-labelledby="body-title"><h2 id="body-title">政策正文</h2><div class="body-text">{{ policy.current_version.body_text }}</div></section>
    <section class="files" aria-labelledby="files-title"><h2 id="files-title">原文与文件</h2><a class="snapshot" :href="policy.current_version.snapshot_url">原始网页快照</a><AttachmentList :attachments="policy.attachments" /></section>
    <section class="evaluation-panel" aria-label="评估区域">
      <p v-if="evaluationError" role="alert" class="evaluation-error">{{ evaluationError }}</p>
      <div v-if="evaluationLoading" class="task-state" role="status">
        <span class="state-marker" aria-hidden="true"></span>
        <div><h2>正在加载评估记录…</h2><p>政策正文已可阅读，评估记录加载完成后将在这里显示。</p></div>
      </div>
      <template v-else-if="currentEvaluation">
        <EvaluationSummary v-if="['succeeded', 'awaiting_confirmation', 'confirmed'].includes(currentEvaluation.status)" :evaluation="currentEvaluation" />
        <EvaluationConfirmationForm
          v-if="canRetry && currentEvaluation.status === 'awaiting_confirmation'"
          :evaluation="currentEvaluation"
          @confirmed="refreshEvaluations(Number(route.params.id))"
        />
        <PrimaryEntitySelector
          v-if="canRetry && currentEvaluation.status === 'confirmed' && policy"
          :policy-id="policy.id"
          :candidates="currentEvaluation.entities.map((entity) => ({ entity_seed_code: entity.entity_seed_code, label: String(currentEvaluation.profile_snapshot.find((profile) => profile.seed_code === entity.entity_seed_code)?.legal_name ?? entity.entity_seed_code) }))"
          :current="primaryEntity"
          @selected="refreshPrimaryEntity(policy.id)"
        />
        <div v-else-if="['pending', 'running'].includes(currentEvaluation.status)" class="task-state" role="status">
          <span class="state-marker" aria-hidden="true"></span>
          <div><h2>评估中</h2><p>后台正在分析政策条件与三家经营主体档案，完成后将在这里显示结果。</p></div>
        </div>
        <div v-if="canRetry && ['pending', 'running'].includes(currentEvaluation.status)" class="evaluation-actions">
          <button ref="cancelButton" type="button" data-cancel-evaluation @click="cancelOpen = true">取消评估</button>
        </div>
        <div v-else-if="currentEvaluation.status === 'failed'" class="task-state failed" role="alert">
          <span class="state-marker" aria-hidden="true"></span>
          <div><h2>评估失败</h2><p>本次评估未生成有效结果。负责人可重新创建评估批次。</p></div>
        </div>
        <div v-if="canRetry && ['succeeded', 'awaiting_confirmation', 'confirmed', 'failed'].includes(currentEvaluation.status)" class="evaluation-actions">
          <button ref="retryButton" type="button" data-retry-evaluation @click="confirmRetryOpen = true">重新评估</button>
        </div>
        <EvaluationHistory :evaluations="historicalEvaluations" :attempt-number-by-id="attemptNumberById" />
      </template>
      <div v-else-if="!evaluationError" class="task-state">
        <span class="state-marker" aria-hidden="true"></span>
        <div><h2>等待评估</h2><p>当前政策尚无评估批次。</p></div>
      </div>
    </section>
    <VersionHistory :versions="versions" />

    <div v-if="confirmRetryOpen" class="dialog-backdrop" @click.self="dismissRetryDialog">
      <section ref="retryDialog" role="dialog" aria-modal="true" :aria-busy="retrying" aria-labelledby="retry-dialog-title" class="confirm-dialog" tabindex="-1" @keydown="handleDialogKeydown">
        <p class="eyebrow">重新评估</p>
        <h2 id="retry-dialog-title">创建新的评估批次？</h2>
        <p>系统将使用当前企业档案重新分析，并创建新的历史批次；已有评估记录不会被修改。</p>
        <div>
          <button type="button" data-cancel-retry class="secondary" :disabled="retrying" @click="dismissRetryDialog">取消</button>
          <button ref="confirmRetryButton" type="button" data-confirm-retry :disabled="retrying" @click="confirmRetry">{{ retrying ? "正在创建…" : "确认重新评估" }}</button>
        </div>
      </section>
    </div>
    <div v-if="cancelOpen" class="dialog-backdrop" @click.self="dismissCancelDialog">
      <section ref="cancelDialog" role="dialog" aria-modal="true" :aria-busy="cancelling" aria-labelledby="cancel-dialog-title" class="confirm-dialog" tabindex="-1" @keydown="handleCancelDialogKeydown">
        <p class="eyebrow">取消评估</p>
        <h2 id="cancel-dialog-title">确认取消本次评估？</h2>
        <p>可选填写取消原因，便于后续追溯。</p>
        <label for="cancel-reason">取消原因（可选）</label>
        <textarea id="cancel-reason" v-model="cancelReason" :disabled="cancelling"></textarea>
        <div>
          <button type="button" data-dismiss-cancel class="secondary" :disabled="cancelling" @click="dismissCancelDialog">保留评估</button>
          <button ref="confirmCancelButton" type="button" data-confirm-cancel :disabled="cancelling" @click="confirmCancellation">{{ cancelling ? "正在取消…" : "确认取消评估" }}</button>
        </div>
      </section>
    </div>
  </article>
</template>

<style scoped>
.policy-detail { max-width: 68rem; margin: 0 auto; color: #1b3352; }.policy-title { display: flex; align-items: start; justify-content: space-between; gap: 2rem; padding-bottom: 1.35rem; border-bottom: 3px solid #1e568c; }.eyebrow { margin: 0 0 .45rem; color: #6a7e95; font-size: .75rem; font-weight: 800; letter-spacing: .09em; }.policy-title h1 { max-width: 48rem; margin: 0; font: 700 clamp(1.8rem, 4vw, 2.65rem)/1.25 "Noto Serif SC", "Songti SC", serif; }.policy-title p:last-child { color: #60758d; }.facts, .document, .files, .evaluation-panel { margin-top: 1.5rem; padding: 1.2rem 1.35rem; border: 1px solid #d8e2ec; background: #fff; }.facts dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 0 0 1rem; }.facts dl div { padding-left: .75rem; border-left: 3px solid #d3a747; }.facts dt { color: #6a7e95; font-size: .75rem; }.facts dd { margin: .3rem 0 0; font-weight: 700; }.facts ul { margin: 0; padding: 0; list-style: none; }.facts li { display: flex; justify-content: space-between; gap: 1rem; padding-top: .8rem; border-top: 1px solid #e3ebf3; }.facts a, .snapshot { color: #14558c; }.document h2, .files > h2, .task-state h2 { margin-top: 0; font: 700 1.2rem/1.4 "Noto Serif SC", "Songti SC", serif; }.body-text { color: #293f58; line-height: 1.9; white-space: pre-wrap; }.task-state { display: flex; align-items: start; gap: .9rem; color: #536b82; }.task-state h2 { margin-bottom: .25rem; }.task-state p { margin: 0; }.state-marker { width: .7rem; height: .7rem; margin-top: .35rem; border: 2px solid #49769a; border-radius: 50%; box-shadow: 0 0 0 4px #e8f0f6; }.failed .state-marker { border-color: #a95345; box-shadow: 0 0 0 4px #faece9; }.evaluation-actions { display: flex; justify-content: flex-end; margin-top: 1rem; }.evaluation-actions button, .confirm-dialog button { padding: .58rem .9rem; color: #fff; border: 1px solid #174f7e; background: #174f7e; font: inherit; font-size: .82rem; font-weight: 800; cursor: pointer; }.evaluation-error, .error { padding: 1rem; color: #9b1c1c; background: #fff1f0; }.dialog-backdrop { position: fixed; z-index: 20; inset: 0; display: grid; place-items: center; padding: 1rem; background: rgb(15 33 50 / 48%); }.confirm-dialog { width: min(28rem, 100%); margin: 0; padding: 1.35rem; border: 0; background: #fff; box-shadow: 0 1.5rem 4rem rgb(8 27 45 / 30%); }.confirm-dialog h2 { margin: 0; font: 700 1.35rem/1.35 "Noto Serif SC", "Songti SC", serif; }.confirm-dialog > p:not(.eyebrow) { color: #536b82; line-height: 1.65; }.confirm-dialog > div { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1.25rem; }.confirm-dialog button.secondary { color: #315671; border-color: #bdcad5; background: #fff; }.confirm-dialog button:disabled { cursor: wait; opacity: .65; }@media (max-width: 700px) { .policy-title { flex-direction: column; }.facts dl { grid-template-columns: 1fr; }.facts li { align-items: start; flex-direction: column; } }
</style>
