<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getBusinessErrorCode } from "../../api/errors";
import { updateBusinessEntity, updateSharedProfile, type BusinessEntityPatchInput, type BusinessEntityResponse, type ProfilePatchInput, type ProfileResponse } from "../../api/profiles";
type SharedEditorProps = { target: "shared"; profile: ProfileResponse };
type EntityEditorProps = { target: "entity"; profile: BusinessEntityResponse };
type EditableProfile = ProfileResponse | BusinessEntityResponse;
const props = defineProps<SharedEditorProps | EntityEditorProps>();
const emit = defineEmits<{ updated: [profile: EditableProfile]; reload: [] }>();
const saving = ref(false); const error = ref(""); const conflict = ref(false); const name = ref(""); const status = ref(""); const dataText = ref("{}");
const isShared = computed(() => props.target === "shared");
function sortedValue(value: unknown): unknown { if (Array.isArray(value)) return value.map(sortedValue); if (value && typeof value === "object") return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, sortedValue(item)])); return value; }
function stableJson(value: Record<string, unknown>): string { return JSON.stringify(sortedValue(value)); }
function syncForm(profile: EditableProfile): void { name.value = "display_name" in profile ? profile.display_name : profile.legal_name; status.value = profile.verification_status; dataText.value = JSON.stringify(profile.data, null, 2); error.value = ""; conflict.value = false; }
function validName(): string | null { const normalized = name.value.trim(); if (!normalized) { error.value = isShared.value ? "公司名称不能为空。" : "企业主体名称不能为空。"; return null; } if (normalized.length > 255) { error.value = "名称不能超过 255 个字符。"; return null; } return normalized; }
function validStatus(): string | null { const normalized = status.value.trim(); if (!normalized) { error.value = "核验状态不能为空。"; return null; } if (normalized.length > 64) { error.value = "核验状态不能超过 64 个字符。"; return null; } if (!/^[a-z0-9_]+$/.test(normalized)) { error.value = "核验状态必须匹配 [a-z0-9_]+。"; return null; } return normalized; }
function isScalar(value: unknown): value is string | number | boolean | null { return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean"; }
function validDataShape(data: Record<string, unknown>): boolean {
  let nodes = 0;
  function visit(value: unknown, depth: number): boolean {
    nodes += 1;
    if (nodes > 64) return false;
    if (isScalar(value)) return true;
    if (depth >= 4) return false;
    if (Array.isArray(value)) {
      return value.length <= 32 && value.every((item) => visit(item, depth + 1));
    }
    if (!value || typeof value !== "object") return false;
    return Object.entries(value as Record<string, unknown>).every(
      ([key, item]) => key.trim().length > 0
        && Array.from(key).length <= 64
        && visit(item, depth + 1),
    );
  }
  return visit(data, 0);
}
function parseData(): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(dataText.value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") { error.value = "档案结构化数据必须是 JSON 对象。"; return null; }
    const data = parsed as Record<string, unknown>;
    if (!validDataShape(data)) { error.value = "档案结构化数据必须是受限递归 JSON（深度 4、节点 64、列表 32 项，键名不超过 64 个字符）。"; return null; }
    if (new TextEncoder().encode(stableJson(data)).byteLength > 32 * 1024) { error.value = "档案结构化数据不能超过 32 KiB。"; return null; }
    return data;
  } catch { error.value = "档案结构化数据不是有效的 JSON 格式。"; return null; }
}
async function submit(): Promise<void> {
  if (saving.value) return; error.value = ""; conflict.value = false;
  const normalizedName = validName(); const normalizedStatus = validStatus(); const data = parseData();
  if (normalizedName === null || normalizedStatus === null || data === null) return;
  saving.value = true;
  try {
    if (props.target === "shared") { const profile = props.profile; const payload: ProfilePatchInput = { expected_version: profile.version }; if (normalizedName !== profile.display_name) payload.display_name = normalizedName; if (stableJson(data) !== stableJson(profile.data)) payload.data = data; if (normalizedStatus !== profile.verification_status) payload.verification_status = normalizedStatus; if (Object.keys(payload).length === 1) { error.value = "没有可保存的变更。"; return; } emit("updated", await updateSharedProfile(payload)); }
    else { const profile = props.profile; const payload: BusinessEntityPatchInput = { expected_version: profile.version }; if (normalizedName !== profile.legal_name) payload.legal_name = normalizedName; if (stableJson(data) !== stableJson(profile.data)) payload.data = data; if (normalizedStatus !== profile.verification_status) payload.verification_status = normalizedStatus; if (Object.keys(payload).length === 1) { error.value = "没有可保存的变更。"; return; } emit("updated", await updateBusinessEntity(profile.seed_code, payload)); }
  } catch (caught) { const businessError = getBusinessErrorCode(caught); conflict.value = businessError?.code === "profile_version_conflict"; error.value = conflict.value ? `资料已被他人更新（当前版本 ${businessError?.currentVersion ?? "未知"}）。重新加载后再编辑。` : "档案未能保存，请稍后重试。"; }
  finally { saving.value = false; }
}
watch(() => props.profile, syncForm, { immediate: true, deep: true });
</script>
<template>
  <form class="profile-editor" @submit.prevent="submit"><label>{{ isShared ? "公司名称" : "企业主体名称" }}<input v-model="name" :aria-label="isShared ? '公司名称' : '企业主体名称'" maxlength="255" required /></label><label>核验状态<input v-model="status" aria-label="核验状态" maxlength="64" required /></label><label>档案结构化数据<textarea v-model="dataText" aria-label="档案结构化数据" /></label><p v-if="error" class="error" role="alert">{{ error }}<button v-if="conflict" type="button" data-reload-profile @click="emit('reload')">重新加载</button></p><button type="submit" :disabled="saving">{{ saving ? "正在保存……" : "保存档案" }}</button></form>
</template>
<style scoped>
.profile-editor{display:grid;gap:.65rem;margin-top:1.1rem;padding:1rem;background:#f8fbfe;border-left:3px solid #1e568c}.profile-editor label{display:grid;gap:.28rem;color:#435d78;font-size:.86rem;font-weight:700}.profile-editor input,.profile-editor textarea{box-sizing:border-box;width:100%;min-height:2.35rem;padding:.45rem .55rem;color:#233f60;border:1px solid #b8c7d8;background:#fff;font:inherit}.profile-editor textarea{min-height:8rem;resize:vertical;font-family:ui-monospace,Consolas,monospace;font-size:.82rem;line-height:1.5}.profile-editor button{justify-self:start;min-height:2.35rem;padding:.42rem .8rem;color:#fff;border:1px solid #113a70;background:#113a70;font:inherit;font-weight:700;cursor:pointer}.profile-editor button:focus-visible{outline:3px solid #e3b260;outline-offset:2px}.profile-editor .error{margin:0;padding:.7rem;color:#9b1c1c;background:#fff1f0;line-height:1.55}.profile-editor .error button{margin-left:.5rem;color:#8a1c1c;border-color:#d69a98;background:#fff}.profile-editor button:disabled{opacity:.6;cursor:wait}@media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>
