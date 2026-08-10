<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";

import { businessErrorMessage } from "../../api/errors";
import {
  createProjectFromPolicy,
  getConvertiblePolicies,
  getProjectUserOptions,
  type ConvertiblePolicyItem,
  type ProjectUserOption,
} from "../../api/projects";
import { currentUser } from "../../auth/state";

const props = defineProps<{ open: boolean; policyId?: number; keyGenerator?: () => string }>();
const emit = defineEmits<{ close: []; created: [projectId: number] }>();
const policies = ref<ConvertiblePolicyItem[]>([]);
const users = ref<ProjectUserOption[]>([]);
const policyPage = ref(1);
const policyTotal = ref(0);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const idempotencyKey = ref<string | null>(null);
const draft = reactive({ policy_id: 0, name: "", liaison_user_id: "", member_user_ids: [] as number[], deadline_on: "" });
const isOwner = computed(() => currentUser.value?.roles.includes("applicant_owner") ?? false);
const selectedPolicy = computed(() => policies.value.find((policy) => policy.id === draft.policy_id) ?? null);
const canSubmit = computed(() => isOwner.value && selectedPolicy.value !== null && Number(draft.liaison_user_id) > 0 && !saving.value);

function createConversionKey(): string {
  const generated = globalThis.crypto?.randomUUID?.();
  return generated ?? `project-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function resetDraft(): void {
  draft.policy_id = 0; draft.name = ""; draft.liaison_user_id = ""; draft.member_user_ids = []; draft.deadline_on = "";
  idempotencyKey.value = null; error.value = "";
}

function selectPolicy(policy: ConvertiblePolicyItem | null): void {
  if (!policy) return;
  draft.policy_id = policy.id;
  draft.name = policy.title;
  draft.deadline_on = policy.deadline_on ?? "";
}

async function loadPolicies(page = 1): Promise<void> {
  if (!isOwner.value) return;
  loading.value = true; error.value = "";
  try {
    let result = await getConvertiblePolicies(props.policyId === undefined ? page : 1, 20);
    if (props.policyId !== undefined) {
      let fixedPolicy = result.items.find((policy) => policy.id === props.policyId) ?? null;
      while (!fixedPolicy && result.page * result.page_size < result.total) {
        result = await getConvertiblePolicies(result.page + 1, 20);
        fixedPolicy = result.items.find((policy) => policy.id === props.policyId) ?? null;
      }
      policies.value = fixedPolicy ? [fixedPolicy] : [];
      policyPage.value = result.page;
      policyTotal.value = fixedPolicy ? 1 : 0;
      selectPolicy(fixedPolicy);
      if (!fixedPolicy) error.value = "当前政策已不符合项目转换条件，请刷新政策详情。";
      return;
    }
    policies.value = result.items;
    policyPage.value = result.page;
    policyTotal.value = result.total;
    if (!selectedPolicy.value) selectPolicy(result.items[0] ?? null);
  } catch {
    error.value = "可转换政策暂时无法加载，请稍后重试。";
  } finally { loading.value = false; }
}

async function openDrawer(): Promise<void> {
  if (!isOwner.value) return;
  try {
    await Promise.all([loadPolicies(), getProjectUserOptions().then((items) => { users.value = items; })]);
  } catch {
    error.value = "创建项目所需的用户列表暂时无法加载，请稍后重试。";
  }
}

function onPolicyChange(): void { selectPolicy(selectedPolicy.value); }
function close(): void { if (!saving.value) { resetDraft(); emit("close"); } }
function warningText(warning: string): string {
  return warning === "deadline_expired" ? "申请截止日期已过，仍可按实际情况创建项目。" : "申请截止日期未知，请核对后再创建项目。";
}

async function submit(): Promise<void> {
  const policy = selectedPolicy.value;
  if (!policy || !canSubmit.value) return;
  saving.value = true; error.value = "";
  idempotencyKey.value ??= props.keyGenerator?.() ?? createConversionKey();
  try {
    const liaisonId = Number(draft.liaison_user_id);
    const memberIds = [...new Set(draft.member_user_ids)].filter((id) => id !== liaisonId);
    const project = await createProjectFromPolicy(policy.id, {
      name: draft.name.trim() || null,
      liaison_user_id: liaisonId,
      member_user_ids: memberIds,
      deadline_on: draft.deadline_on || null,
    }, idempotencyKey.value);
    const projectId = project.id;
    resetDraft();
    emit("created", projectId);
  } catch (caught) {
    error.value = businessErrorMessage(caught, "创建项目未完成，请稍后重试。");
  } finally { saving.value = false; }
}

watch(() => props.open, (open) => { if (open) void openDrawer(); else resetDraft(); }, { immediate: true });
</script>

<template>
  <el-drawer v-if="isOwner" :model-value="open" :append-to-body="true" size="min(42rem, 100%)" @close="close">
    <template #header><h2>将政策转为项目</h2></template>
    <form class="project-create-form" @submit.prevent="submit">
      <p v-if="loading" role="status">正在加载可转换政策…</p>
      <template v-else>
        <label>可转换政策<select v-model.number="draft.policy_id" aria-label="可转换政策" required :disabled="policyId !== undefined" @change="onPolicyChange"><option v-for="policy in policies" :key="policy.id" :value="policy.id">{{ policy.title }}</option></select></label>
        <div v-if="selectedPolicy" class="inherited-facts"><p><strong>主申报企业</strong>{{ selectedPolicy.primary_entity_legal_name }}（{{ selectedPolicy.primary_entity_seed_code }}）</p><p><strong>申请截止</strong>{{ selectedPolicy.deadline_on ?? "未注明" }}</p></div>
        <p v-for="warning in selectedPolicy?.conversion_warnings ?? []" :key="warning" class="deadline-warning">{{ warningText(warning) }}</p>
        <label>项目名称<input v-model="draft.name" maxlength="255" /></label>
        <label>项目截止日期<input v-model="draft.deadline_on" type="date" /></label>
        <label>项目对接人<select v-model="draft.liaison_user_id" aria-label="项目对接人" required><option value="">请选择</option><option v-for="user in users" :key="user.id" :value="String(user.id)">{{ user.display_name }}</option></select></label>
        <label>项目成员（可选）<select v-model="draft.member_user_ids" aria-label="项目成员" multiple><option v-for="user in users" :key="user.id" :value="user.id">{{ user.display_name }}</option></select></label>
        <p v-if="!policies.length" class="empty">当前没有可转换的政策。</p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <div class="drawer-actions"><button type="button" :disabled="saving" @click="close">取消</button><button type="submit" :disabled="!canSubmit">{{ saving ? "正在创建…" : "创建项目" }}</button></div>
        <nav v-if="policyId === undefined && policyTotal > 20" class="policy-pages" aria-label="可转换政策分页"><button type="button" :disabled="policyPage === 1" @click="loadPolicies(policyPage - 1)">上一页</button><span>第 {{ policyPage }} 页</span><button type="button" :disabled="policyPage * 20 >= policyTotal" @click="loadPolicies(policyPage + 1)">下一页</button></nav>
      </template>
    </form>
  </el-drawer>
</template>

<style scoped>
h2 { margin: 0; color: #1b3352; font-family: "Noto Serif SC", "Songti SC", serif; }.project-create-form { display: grid; gap: .75rem; color: #29435f; }.project-create-form label { display: grid; gap: .3rem; font-size: .88rem; font-weight: 700; }.project-create-form input, .project-create-form select { box-sizing: border-box; width: 100%; min-height: 2.45rem; padding: .45rem .6rem; border: 1px solid #b8c7d8; background: #fff; }.project-create-form select[multiple] { min-height: 6rem; }.inherited-facts { padding: .7rem .85rem; border-left: 3px solid #174f7e; background: #eef5fa; }.inherited-facts p { margin: .2rem 0; }.inherited-facts strong { display: block; color: #60758d; font-size: .75rem; }.deadline-warning { margin: 0; padding: .65rem .8rem; color: #79530e; background: #fff8e9; border-left: 3px solid #d4a449; }.form-error { margin: 0; padding: .7rem; color: #9b1c1c; background: #fff1f0; }.drawer-actions, .policy-pages { display: flex; justify-content: flex-end; align-items: center; gap: .7rem; }.drawer-actions button, .policy-pages button { min-height: 2.35rem; padding: .42rem .8rem; color: #174f7e; border: 1px solid #9db5cd; background: #fff; font: inherit; font-weight: 700; cursor: pointer; }.drawer-actions button[type="submit"] { color: #fff; border-color: #113a70; background: #113a70; }.drawer-actions button:disabled, .policy-pages button:disabled { cursor: not-allowed; opacity: .6; } input:focus-visible, select:focus-visible, button:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }
</style>
