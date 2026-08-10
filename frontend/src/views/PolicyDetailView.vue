<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import {
  createEvaluation,
  cancelEvaluation,
  getEvaluations,
  getPrimaryEntityHistory,
  type EvaluationBatch,
  type PrimaryEntityDecision,
} from "../api/evaluations";
import { useEvaluationPolling } from "../composables/useEvaluationPolling";
import {
  getPolicy,
  getPolicyConclusionHistory,
  getPolicyVersions,
  type PolicyConclusion,
  type PolicyConclusionDecision,
  type PolicyDetail,
  type PolicyVersion,
} from "../api/policies";
import { currentUser } from "../auth/state";
import EvaluationHistory from "../components/evaluations/EvaluationHistory.vue";
import EvaluationSummary from "../components/evaluations/EvaluationSummary.vue";
import EvaluationConfirmationForm from "../components/evaluations/EvaluationConfirmationForm.vue";
import PolicyConclusionDecisionForm from "../components/evaluations/PolicyConclusionDecisionForm.vue";
import PolicyConclusionHistory from "../components/evaluations/PolicyConclusionHistory.vue";
import PrimaryEntitySelector from "../components/evaluations/PrimaryEntitySelector.vue";
import AttachmentList from "../components/policies/AttachmentList.vue";
import ConclusionBadge from "../components/policies/ConclusionBadge.vue";
import VersionHistory from "../components/policies/VersionHistory.vue";
import ProjectCreateDrawer from "../components/projects/ProjectCreateDrawer.vue";

const route = useRoute();
const router = useRouter();
const policy = ref<PolicyDetail | null>(null);
const versions = ref<PolicyVersion[]>([]);
const evaluations = ref<EvaluationBatch[]>([]);
const loading = ref(true);
const error = ref("");
const evaluationError = ref("");
const evaluationLoading = ref(true);
const primaryEntity = ref<PrimaryEntityDecision | null>(null);
const primaryEntityLoading = ref(true);
const conclusionHistory = ref<PolicyConclusionDecision[]>([]);
const conclusionDecisionOpen = ref(false);
const conversionOpen = ref(false);
const mobile = ref(false);
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
let mobileQuery: MediaQueryList | null = null;
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
const canConvertPolicy = computed(() => canRetry.value
  && policy.value?.conclusion_confirmed === true
  && policy.value.current_conclusion === "recommend_apply"
  && !policy.value.converted_to_project
  && primaryEntity.value !== null);
const canRetryCurrent = computed(
  () => canRetry.value
    && currentEvaluation.value !== null
    && ["succeeded", "awaiting_confirmation", "confirmed", "failed", "cancelled"].includes(currentEvaluation.value.status),
);
const confirmedConclusion = computed<PolicyConclusion | null>(() => {
  const value = policy.value?.current_conclusion;
  return value && value !== "pending_confirmation" ? value : null;
});
const conclusionLabels: Record<string, string> = {
  recommend_apply: "建议申报",
  watch: "持续关注",
  not_recommended: "暂不建议申报",
  uncertain: "无法判断",
};
const sourceLabels: Record<string, string> = {
  evaluation_confirmation: "负责人确认",
  manual_override: "负责人调整",
  system_suggestion: "系统建议",
};
const isEvaluationActive = computed(
  () => currentEvaluation.value !== null && ["pending", "running"].includes(currentEvaluation.value.status),
);
function formatDate(value: string | null) { return value ?? "未注明"; }
function formatTime(value: string) { return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function updateMobile(): void {
  mobile.value = mobileQuery?.matches ?? window.innerWidth <= 720;
  if (mobile.value) conversionOpen.value = false;
}
async function projectCreated(projectId: number): Promise<void> {
  conversionOpen.value = false;
  await router.push(`/projects/${projectId}`);
}

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
  primaryEntityLoading.value = true;
  try {
    const history = await getPrimaryEntityHistory(id);
    primaryEntity.value = history.find((decision) => decision.is_current) ?? null;
  } catch {
    primaryEntity.value = null;
  } finally {
    primaryEntityLoading.value = false;
  }
}

async function refreshConclusionHistory(id: number): Promise<void> {
  try {
    conclusionHistory.value = await getPolicyConclusionHistory(id);
  } catch {
    conclusionHistory.value = [];
  }
}

async function refreshConclusionState(id: number): Promise<void> {
  const [updatedPolicy] = await Promise.all([
    getPolicy(id),
    refreshEvaluations(id),
    refreshPrimaryEntity(id),
    refreshConclusionHistory(id),
  ]);
  policy.value = updatedPolicy;
  conclusionDecisionOpen.value = false;
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
    evaluationError.value = "无法取消本次评估，请稍后重试。";
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
  const focusable = Array.from(
    cancelDialog.value.querySelectorAll<HTMLElement>("textarea:not(:disabled), button:not(:disabled)"),
  );
  if (!focusable.length) {
    event.preventDefault();
    cancelDialog.value.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
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
  if (typeof window.matchMedia === "function") {
    mobileQuery = window.matchMedia("(max-width: 720px)");
    mobileQuery.addEventListener("change", updateMobile);
  }
  updateMobile();
  const id = Number(route.params.id);
  try {
    [policy.value, versions.value] = await Promise.all([getPolicy(id), getPolicyVersions(id)]);
    void refreshEvaluations(id);
    void refreshPrimaryEntity(id);
    void refreshConclusionHistory(id);
  }
  catch { error.value = "无法加载政策详情。请返回政策中心后重试。"; }
  finally { loading.value = false; }
});
onBeforeUnmount(() => mobileQuery?.removeEventListener("change", updateMobile));
</script>

<template>
  <p v-if="loading" role="status">正在加载政策详情…</p>
  <p v-else-if="error" role="alert" class="error">{{ error }}</p>
  <article v-else-if="policy" class="policy-detail">
    <header class="policy-title">
      <div><p class="eyebrow">政策档案 · 当前版本 {{ policy.current_version.version_number }}</p><h1>{{ policy.title }}</h1><p v-if="policy.document_number">{{ policy.document_number }}</p></div>
      <ConclusionBadge :conclusion="policy.current_conclusion" :confirmed="policy.conclusion_confirmed" />
    </header>
    <section class="project-lifecycle" aria-label="项目状态">
      <RouterLink v-if="policy.converted_to_project && policy.project_id" :to="`/projects/${policy.project_id}`">
        已转项目：{{ policy.project_name ?? `项目 #${policy.project_id}` }}
      </RouterLink>
      <button v-else-if="canConvertPolicy && !mobile" type="button" data-open-project-conversion @click="conversionOpen = true">
        转为项目
      </button>
    </section>
    <section v-if="policy.conclusion_confirmed && confirmedConclusion" data-conclusion-metadata class="conclusion-metadata" aria-label="当前政策结论">
      <dl>
        <div><dt>当前结论：</dt><dd>{{ conclusionLabels[confirmedConclusion] }}</dd></div>
        <div><dt>来源：</dt><dd>{{ sourceLabels[policy.current_conclusion_source] }}</dd></div>
        <div><dt>确认时间：</dt><dd>{{ policy.conclusion_confirmed_at ? formatTime(policy.conclusion_confirmed_at) : "未注明" }}</dd></div>
      </dl>
      <button v-if="canRetry" type="button" data-open-conclusion-decision @click="conclusionDecisionOpen = !conclusionDecisionOpen">
        {{ conclusionDecisionOpen ? "收起调整" : "调整政策结论" }}
      </button>
      <PolicyConclusionDecisionForm
        v-if="canRetry && conclusionDecisionOpen"
        :policy-id="policy.id"
        :current-conclusion="confirmedConclusion"
        :has-primary-entity="primaryEntity !== null"
        @decided="refreshConclusionState(policy.id)"
      />
      <PolicyConclusionHistory :decisions="conclusionHistory" />
    </section>
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
          v-if="canRetry && currentEvaluation.status === 'awaiting_confirmation' && !primaryEntityLoading"
          :evaluation="currentEvaluation"
          :current-primary-entity-seed-code="primaryEntity?.entity_seed_code ?? null"
          @confirmed="refreshConclusionState(Number(route.params.id))"
        />
        <div v-else-if="canRetry && currentEvaluation.status === 'awaiting_confirmation'" class="task-state" role="status">
          <span class="state-marker" aria-hidden="true"></span>
          <div><h2>正在加载主申报企业信息…</h2><p>加载完成后即可确认本次评估。</p></div>
        </div>
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
        <div v-else-if="currentEvaluation.status === 'cancelled'" class="task-state cancelled" role="status">
          <span class="state-marker" aria-hidden="true"></span>
          <div>
            <h2>已取消</h2>
            <p>第 {{ attemptNumberById[currentEvaluation.id] }} 次评估 · 批次 #{{ currentEvaluation.id }} 已取消，不会继续运行。</p>
          </div>
        </div>
        <div v-if="canRetryCurrent" class="evaluation-actions">
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
    <ProjectCreateDrawer v-if="canConvertPolicy && !mobile && conversionOpen" :open="conversionOpen" :policy-id="policy.id" @close="conversionOpen = false" @created="projectCreated" />

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
.conclusion-metadata{margin-top:1rem;padding:1rem 1.35rem;border-left:4px solid #174f7e;background:#eef5fa}.conclusion-metadata dl{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:0}.conclusion-metadata dt{color:#60758d;font-size:.75rem}.conclusion-metadata dd{margin:.25rem 0 0;font-weight:800}.conclusion-metadata>button{margin-top:1rem;padding:.55rem .85rem;color:#174f7e;border:1px solid #174f7e;background:#fff;font:inherit;font-weight:800}@media(max-width:700px){.conclusion-metadata dl{grid-template-columns:1fr}}
.project-lifecycle{display:flex;justify-content:flex-end;min-height:1.5rem;margin-top:.75rem}.project-lifecycle a,.project-lifecycle button{color:#174f7e;font:inherit;font-size:.86rem;font-weight:800;text-decoration:underline;text-underline-offset:3px}.project-lifecycle button{padding:.15rem 0;border:0;background:transparent;cursor:pointer}.project-lifecycle button:focus-visible,.project-lifecycle a:focus-visible{outline:3px solid #e3b260;outline-offset:3px}@media(max-width:720px){.project-lifecycle{justify-content:flex-start}}
</style>
