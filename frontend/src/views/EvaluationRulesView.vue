<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import {
  createRuleDraft,
  listEvaluationRules,
  type EvaluationRuleSet,
} from "../api/evaluationRules";
import { currentUser } from "../auth/state";

const router = useRouter();
const rules = ref<EvaluationRuleSet[]>([]);
const loading = ref(true);
const error = ref("");
const creating = ref(false);
const createOpen = ref(false);
const name = ref("");
const description = ref("");
const canManage = computed(
  () => currentUser.value?.roles.includes("applicant_owner") ?? false,
);

function publishedVersion(rule: EvaluationRuleSet) {
  return rule.versions.find((version) => version.status === "published") ?? null;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function loadRules() {
  loading.value = true;
  error.value = "";
  try {
    rules.value = await listEvaluationRules();
  } catch {
    error.value = "评估规则暂时无法加载，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

async function createRule() {
  if (!name.value.trim() || creating.value) return;
  creating.value = true;
  error.value = "";
  try {
    const created = await createRuleDraft({
      name: name.value.trim(),
      description: description.value.trim() || null,
      prompt_version: "stage2-decision-v1",
      hard_rules: [],
      weighted_rules: [],
    });
    if ("versions" in created) await router.push(`/evaluation-rules/${created.id}`);
  } catch {
    error.value = "无法新建规则，请检查名称后重试。";
  } finally {
    creating.value = false;
  }
}

onMounted(loadRules);
</script>

<template>
  <section class="rules-page" aria-labelledby="rules-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">决策依据 · 不可变版本</p>
        <h1 id="rules-title">评估规则</h1>
        <p>发布后的规则固定进入评估历史；调整规则时创建新版本，不改写旧批次。</p>
      </div>
      <button v-if="canManage" class="primary-action" type="button" @click="createOpen = true">
        新建规则
      </button>
    </header>

    <form v-if="createOpen" class="create-panel" @submit.prevent="createRule">
      <label>规则名称<input v-model="name" maxlength="255" required /></label>
      <label>说明<textarea v-model="description" maxlength="2000" rows="2" /></label>
      <div class="panel-actions">
        <button type="button" @click="createOpen = false">取消</button>
        <button class="primary-action" type="submit" :disabled="creating || !name.trim()">
          {{ creating ? "正在创建…" : "创建草稿" }}
        </button>
      </div>
    </form>

    <p v-if="loading" class="status-message" role="status">正在加载评估规则…</p>
    <p v-else-if="error" class="status-message error" role="alert">{{ error }}</p>
    <section v-else-if="rules.length === 0" class="empty-state">
      <h2>尚未建立评估规则</h2>
      <p>负责人可以先创建草稿，配置硬性条件和总计 100% 的评分条件。</p>
    </section>
    <div v-else class="rule-list">
      <article v-for="rule in rules" :key="rule.id" class="rule-card">
        <div class="rule-main">
          <p class="rule-kicker">规则集 #{{ rule.id }}</p>
          <h2>
            <RouterLink :to="`/evaluation-rules/${rule.id}`">{{ rule.name }}</RouterLink>
          </h2>
          <p>{{ rule.description || "暂无说明" }}</p>
        </div>
        <dl class="rule-facts">
          <div>
            <dt>当前状态</dt>
            <dd :class="['status-chip', publishedVersion(rule) ? 'published' : 'draft']">
              {{ publishedVersion(rule) ? `当前发布版 V${publishedVersion(rule)?.version_number}` : "尚未发布" }}
            </dd>
          </div>
          <div><dt>版本数量</dt><dd>{{ rule.versions.length }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ formatTime(rule.updated_at) }}</dd></div>
        </dl>
        <RouterLink class="detail-link" :to="`/evaluation-rules/${rule.id}`">
          {{ canManage ? "管理版本" : "查看规则" }}
        </RouterLink>
      </article>
    </div>
  </section>
</template>

<style scoped>
.rules-page { max-width: 76rem; margin: 0 auto; color: #1b3352; }
.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 1.5rem; margin-bottom: 1.5rem; padding-bottom: 1.1rem; border-bottom: 2px solid #1e568c; }
.eyebrow, .rule-kicker { margin: 0 0 .4rem; color: #6a7e95; font-size: .76rem; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; }
h1, h2 { margin-top: 0; font-family: "Noto Serif SC", "Songti SC", serif; }
h1 { margin-bottom: .55rem; font-size: clamp(1.75rem, 3vw, 2.45rem); }
.page-heading p:last-child { max-width: 50rem; margin: 0; color: #526a86; line-height: 1.65; }
.primary-action, .panel-actions button { min-height: 2.35rem; padding: .45rem .8rem; border: 1px solid #9db5cd; border-radius: .2rem; background: #fff; color: #1e568c; cursor: pointer; }
.primary-action { border-color: #113a70; background: #113a70; color: #fff; }
.create-panel { display: grid; gap: 1rem; margin-bottom: 1rem; padding: 1rem; border: 1px solid #d6e1ec; border-top: 4px solid #d4a449; background: #fff; }
.create-panel label { display: grid; gap: .35rem; color: #526a86; font-size: .86rem; font-weight: 700; }
.create-panel input, .create-panel textarea { padding: .65rem; border: 1px solid #b8c8d8; font: inherit; }
.panel-actions { display: flex; justify-content: flex-end; gap: .5rem; }
.rule-list { display: grid; gap: .85rem; }
.rule-card { display: grid; grid-template-columns: minmax(16rem, 1.3fr) minmax(24rem, 1fr) auto; align-items: center; gap: 1.5rem; padding: 1.15rem 1.25rem; border: 1px solid #d6e1ec; border-left: 4px solid #1e568c; background: #fff; box-shadow: 0 .35rem .9rem rgb(25 58 94 / 5%); }
.rule-main h2 { margin-bottom: .35rem; font-size: 1.18rem; }
.rule-main h2 a, .detail-link { color: #164f84; }
.rule-main > p:last-child { margin: 0; color: #60758d; line-height: 1.55; }
.rule-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .8rem; margin: 0; }
.rule-facts dt { margin-bottom: .3rem; color: #718399; font-size: .72rem; font-weight: 700; }
.rule-facts dd { margin: 0; font-size: .84rem; }
.status-chip { display: inline-block; padding: .2rem .45rem; border-radius: 99px; font-weight: 700; }
.status-chip.published { color: #17633c; background: #e8f6ed; }
.status-chip.draft { color: #79530e; background: #fff8e9; }
.detail-link { font-size: .86rem; font-weight: 700; white-space: nowrap; }
.status-message, .empty-state { padding: 1.15rem; border: 1px solid #d6e1ec; background: #fff; }
.status-message.error { color: #9b1c1c; border-color: #f1b8b5; background: #fff1f0; }
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .6; }
@media (max-width: 900px) { .rule-card { grid-template-columns: 1fr; gap: 1rem; }.rule-facts { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px) { .page-heading { align-items: stretch; flex-direction: column; }.primary-action { width: 100%; }.rule-facts { grid-template-columns: 1fr; } }
</style>
