<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import {
  createRuleDraft,
  getEvaluationRule,
  publishRuleVersion,
  retireRuleVersion,
  updateRuleDraft,
  type EvaluationRuleDraftInput,
  type EvaluationRuleSet,
  type EvaluationRuleVersion,
} from "../api/evaluationRules";
import { currentUser } from "../auth/state";

const route = useRoute();
const rule = ref<EvaluationRuleSet | null>(null);
const form = ref<EvaluationRuleDraftInput | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const canManage = computed(() => currentUser.value?.roles.includes("applicant_owner") ?? false);
const currentDraft = computed(() => rule.value?.versions.find((item) => item.status === "draft") ?? null);
const publishedVersion = computed(() => rule.value?.versions.find((item) => item.status === "published") ?? null);
const enabledWeightTotal = computed(() => form.value?.weighted_rules.filter((item) => item.enabled).reduce((sum, item) => sum + Number(item.weight || 0), 0) ?? 0);
const canPublish = computed(() => canManage.value && currentDraft.value !== null && enabledWeightTotal.value === 100 && !saving.value);

function toForm(version: EvaluationRuleVersion): EvaluationRuleDraftInput {
  return {
    name: rule.value?.name ?? "",
    description: rule.value?.description ?? null,
    prompt_version: version.prompt_version,
    hard_rules: version.hard_rules.map((item) => ({ ...item })),
    weighted_rules: version.weighted_rules.map((item) => ({ ...item })),
  };
}

function statusLabel(status: EvaluationRuleVersion["status"]) {
  return { draft: "草稿", published: "已发布", retired: "已停用" }[status];
}

function formatTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

async function loadRule() {
  loading.value = true;
  error.value = "";
  try {
    rule.value = await getEvaluationRule(Number(route.params.id));
    const editable = currentDraft.value ?? rule.value.versions[0];
    form.value = editable ? toForm(editable) : null;
  } catch {
    error.value = "评估规则暂时无法加载，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

function addHardRule() {
  form.value?.hard_rules.push({ code: `HARD_${(form.value?.hard_rules.length ?? 0) + 1}`, name: "", instruction: "", enabled: true });
}

function addWeightedRule() {
  form.value?.weighted_rules.push({ code: `SCORE_${(form.value?.weighted_rules.length ?? 0) + 1}`, name: "", instruction: "", weight: 1, enabled: true });
}

async function runAction(action: () => Promise<unknown>, success: string) {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    await action();
    notice.value = success;
    await loadRule();
  } catch {
    error.value = "操作未完成，请检查规则内容后重试。";
  } finally {
    saving.value = false;
  }
}

async function saveDraft() {
  if (!currentDraft.value || !form.value) return;
  await runAction(() => updateRuleDraft(currentDraft.value!.id, form.value!), "草稿已保存。");
}

async function publishDraft() {
  if (!canPublish.value || !currentDraft.value) return;
  if (!window.confirm("发布后该版本不可编辑，确定发布吗？")) return;
  await runAction(() => publishRuleVersion(currentDraft.value!.id), "规则版本已发布。");
}

async function createNextVersion() {
  if (!rule.value || !form.value || currentDraft.value) return;
  await runAction(() => createRuleDraft(form.value!, rule.value!.id), "新版本草稿已创建。");
}

async function retirePublished() {
  if (!publishedVersion.value) return;
  if (!window.confirm("停用后，新评估将无法使用该版本。确定停用吗？")) return;
  await runAction(() => retireRuleVersion(publishedVersion.value!.id), "已发布版本已停用。");
}

onMounted(loadRule);
</script>

<template>
  <section class="rule-page" aria-labelledby="rule-title">
    <p v-if="loading" class="status-message" role="status">正在加载规则…</p>
    <p v-else-if="error && !rule" class="status-message error" role="alert">{{ error }}</p>
    <template v-else-if="rule">
      <header class="page-heading">
        <div>
          <RouterLink to="/evaluation-rules" class="back-link">← 返回评估规则</RouterLink>
          <p class="eyebrow">规则集 #{{ rule.id }} · {{ rule.versions.length }} 个版本</p>
          <h1 id="rule-title">{{ rule.name }}</h1>
          <p>{{ rule.description || "暂无说明" }}</p>
        </div>
        <div v-if="canManage" class="heading-actions">
          <button v-if="!currentDraft" type="button" :disabled="saving || !form" @click="createNextVersion">创建新版本</button>
          <button v-if="publishedVersion" type="button" :disabled="saving" @click="retirePublished">停用当前版本</button>
        </div>
      </header>

      <p v-if="error" class="status-message error" role="alert">{{ error }}</p>
      <p v-if="notice" class="status-message success" role="status">{{ notice }}</p>

      <div class="rule-layout">
        <form v-if="form" class="editor" @submit.prevent="saveDraft">
          <div class="editor-heading">
            <div><p class="eyebrow">{{ currentDraft ? `编辑草稿 V${currentDraft.version_number}` : "规则内容只读" }}</p><h2>条件配置</h2></div>
            <strong :class="['weight-total', { invalid: enabledWeightTotal !== 100 }]">启用权重合计 {{ enabledWeightTotal }}%</strong>
          </div>

          <fieldset :disabled="!canManage || !currentDraft || saving">
            <legend>基本信息</legend>
            <label>规则名称<input v-model="form.name" maxlength="255" required /></label>
            <label>说明<textarea v-model="form.description" maxlength="2000" rows="2" /></label>
            <label>提示词版本<input v-model="form.prompt_version" maxlength="64" required /></label>
          </fieldset>

          <section class="rule-section">
            <div class="section-heading"><div><p class="section-index">A</p><h3>硬性条件</h3></div><button v-if="canManage && currentDraft" type="button" @click="addHardRule">添加条件</button></div>
            <article v-for="(item, index) in form.hard_rules" :key="`${item.code}-${index}`" class="condition-row">
              <input v-model="item.code" aria-label="硬性条件编码" placeholder="REGION" :disabled="!canManage || !currentDraft" />
              <input v-model="item.name" aria-label="硬性条件名称" placeholder="条件名称" :disabled="!canManage || !currentDraft" />
              <textarea v-model="item.instruction" aria-label="硬性条件说明" placeholder="判断说明" rows="2" :disabled="!canManage || !currentDraft" />
              <label class="toggle"><input v-model="item.enabled" type="checkbox" :disabled="!canManage || !currentDraft" />启用</label>
              <button v-if="canManage && currentDraft" type="button" @click="form.hard_rules.splice(index, 1)">移除</button>
            </article>
          </section>

          <section class="rule-section">
            <div class="section-heading"><div><p class="section-index">B</p><h3>评分条件</h3></div><button v-if="canManage && currentDraft" type="button" @click="addWeightedRule">添加评分项</button></div>
            <article v-for="(item, index) in form.weighted_rules" :key="`${item.code}-${index}`" class="condition-row weighted">
              <input v-model="item.code" aria-label="评分条件编码" placeholder="TECH_MATCH" :disabled="!canManage || !currentDraft" />
              <input v-model="item.name" aria-label="评分条件名称" placeholder="评分项名称" :disabled="!canManage || !currentDraft" />
              <textarea v-model="item.instruction" aria-label="评分条件说明" placeholder="评分说明" rows="2" :disabled="!canManage || !currentDraft" />
              <label class="weight"><input v-model.number="item.weight" type="number" min="1" max="100" :disabled="!canManage || !currentDraft" />%</label>
              <label class="toggle"><input v-model="item.enabled" type="checkbox" :disabled="!canManage || !currentDraft" />启用</label>
              <button v-if="canManage && currentDraft" type="button" @click="form.weighted_rules.splice(index, 1)">移除</button>
            </article>
          </section>

          <div v-if="canManage && currentDraft" class="editor-actions">
            <button type="submit" :disabled="saving">保存草稿</button>
            <button class="publish-action" data-action="publish" type="button" :disabled="!canPublish" @click="publishDraft">发布版本</button>
          </div>
        </form>

        <aside class="version-rail" aria-labelledby="version-history-title">
          <p class="eyebrow">不可变记录</p><h2 id="version-history-title">版本轨道</h2>
          <ol>
            <li v-for="version in rule.versions" :key="version.id" :class="version.status">
              <span class="rail-dot" aria-hidden="true" />
              <div><strong>V{{ version.version_number }} · {{ statusLabel(version.status) }}</strong><p>提示词 {{ version.prompt_version }}</p><time>{{ formatTime(version.published_at || version.created_at) }}</time></div>
            </li>
          </ol>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.rule-page{max-width:82rem;margin:0 auto;color:#1b3352}.page-heading{display:flex;align-items:end;justify-content:space-between;gap:1.5rem;margin-bottom:1.4rem;padding-bottom:1.1rem;border-bottom:2px solid #1e568c}.back-link{display:inline-block;margin-bottom:.9rem;color:#1e568c;font-size:.86rem}.eyebrow,.section-index{margin:0 0 .35rem;color:#6a7e95;font-size:.74rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}h1,h2,h3{margin-top:0;font-family:"Noto Serif SC","Songti SC",serif}h1{margin-bottom:.45rem;font-size:clamp(1.75rem,3vw,2.4rem)}h2{margin-bottom:0;font-size:1.3rem}h3{margin-bottom:0;font-size:1.05rem}.page-heading p:last-child{max-width:50rem;margin:0;color:#526a86}.heading-actions,.editor-actions{display:flex;flex-wrap:wrap;gap:.55rem}button{min-height:2.25rem;padding:.42rem .72rem;border:1px solid #9db5cd;border-radius:.2rem;background:#fff;color:#1e568c;cursor:pointer}button:disabled{cursor:not-allowed;opacity:.52}.rule-layout{display:grid;grid-template-columns:minmax(0,1fr) 18rem;gap:1.25rem;align-items:start}.editor,.version-rail{border:1px solid #d6e1ec;background:#fff;box-shadow:0 .4rem 1rem rgb(25 58 94 / 5%)}.editor{padding:clamp(1rem,2.5vw,1.6rem)}.editor-heading,.section-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.weight-total{padding:.45rem .65rem;color:#17633c;background:#e8f6ed;font-size:.82rem}.weight-total.invalid{color:#8a4c08;background:#fff4db}fieldset{display:grid;gap:.8rem;margin:1.25rem 0;padding:1rem;border:1px solid #dfe7ef}legend{padding:0 .35rem;color:#526a86;font-size:.82rem;font-weight:800}fieldset label{display:grid;gap:.3rem;color:#60758d;font-size:.82rem;font-weight:700}input,textarea{min-width:0;padding:.58rem .62rem;border:1px solid #b8c8d8;background:#fff;color:#1b3352;font:inherit}input:disabled,textarea:disabled{border-color:#dde5ed;background:#f7f9fb;color:#526a86}.rule-section{margin-top:1.3rem;padding-top:1.15rem;border-top:1px solid #dfe7ef}.section-heading>div{display:flex;align-items:baseline;gap:.65rem}.section-index{color:#b77a14;font-size:1rem}.condition-row{display:grid;grid-template-columns:8.5rem 10rem minmax(13rem,1fr) auto auto;gap:.55rem;align-items:center;margin-top:.7rem}.condition-row.weighted{grid-template-columns:8.5rem 9rem minmax(12rem,1fr) 5rem auto auto}.toggle,.weight{display:flex;align-items:center;gap:.3rem;color:#526a86;font-size:.78rem;white-space:nowrap}.toggle input{min-width:auto}.weight input{width:3.2rem}.editor-actions{justify-content:flex-end;margin-top:1.4rem;padding-top:1rem;border-top:1px solid #dfe7ef}.publish-action{border-color:#113a70;background:#113a70;color:#fff}.version-rail{padding:1.2rem;border-top:4px solid #d4a449}.version-rail ol{margin:1.2rem 0 0;padding:0;list-style:none}.version-rail li{position:relative;display:grid;grid-template-columns:1rem 1fr;gap:.6rem;min-height:5rem;color:#60758d}.version-rail li::before{position:absolute;top:.8rem;bottom:-.2rem;left:.31rem;width:1px;background:#cbd8e5;content:""}.version-rail li:last-child::before{display:none}.rail-dot{position:relative;z-index:1;width:.65rem;height:.65rem;margin-top:.25rem;border:2px solid #8ca3ba;border-radius:50%;background:#fff}.published .rail-dot{border-color:#23724a;background:#cdebd8}.draft .rail-dot{border-color:#b77a14;background:#fff0c9}.version-rail strong{color:#233f60;font-size:.88rem}.version-rail p,.version-rail time{display:block;margin:.25rem 0 0;font-size:.75rem}.status-message{padding:1rem;border:1px solid #d6e1ec;background:#fff}.status-message.error{color:#9b1c1c;border-color:#f1b8b5;background:#fff1f0}.status-message.success{color:#17633c;border-color:#b9dfc7;background:#eff9f2}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid #e3b260;outline-offset:2px}@media(max-width:1050px){.rule-layout{grid-template-columns:1fr}.version-rail{order:-1}.condition-row,.condition-row.weighted{grid-template-columns:1fr 1fr}.condition-row textarea{grid-column:1/-1}}@media(max-width:720px){.page-heading,.editor-heading,.section-heading{align-items:stretch;flex-direction:column}.condition-row,.condition-row.weighted{grid-template-columns:1fr}.condition-row textarea{grid-column:auto}.heading-actions button,.editor-actions button{flex:1}}
</style>
