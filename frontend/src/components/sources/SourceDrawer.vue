<script setup lang="ts">
import { reactive, watch } from "vue";

import type { SourceCreateInput } from "../../api/sources";

const props = defineProps<{ open: boolean; saving?: boolean; error?: string }>();
const emit = defineEmits<{ close: []; save: [payload: SourceCreateInput] }>();
const draft = reactive({ name: "", entry_url: "", region_labels: "", topic_labels: "" });

function resetDraft() { draft.name = ""; draft.entry_url = ""; draft.region_labels = ""; draft.topic_labels = ""; }
function normalizeLabels(value: string): string[] { return Array.from(new Set(value.split(",").map((label) => label.trim()).filter((label) => label.length > 0))).slice(0, 20); }
function submit() {
  emit("save", { name: draft.name.trim(), entry_url: draft.entry_url.trim(), region_labels: normalizeLabels(draft.region_labels), topic_labels: normalizeLabels(draft.topic_labels) });
}
watch(() => props.open, (open) => { if (open) resetDraft(); }, { immediate: true });
</script>

<template>
  <el-drawer :model-value="open" :append-to-body="true" size="min(42rem, 100%)" @close="emit('close')">
    <template #header><h2>添加政策来源</h2></template>
    <form class="source-form" @submit.prevent="submit">
      <p class="form-intro">提交公开入口后，系统会先识别并提供安全预览；确认后才可启用采集。</p>
      <label for="source-name">来源名称</label>
      <input id="source-name" v-model="draft.name" required maxlength="255" autocomplete="off" />
      <label for="source-entry-url">公开入口 URL</label>
      <input id="source-entry-url" v-model="draft.entry_url" required type="url" maxlength="2048" placeholder="https://" />
      <label for="source-region-labels">地区标签（可选，逗号分隔）</label>
      <input id="source-region-labels" v-model="draft.region_labels" maxlength="1024" autocomplete="off" placeholder="例如：广东, 深圳" />
      <label for="source-topic-labels">主题标签（可选，逗号分隔）</label>
      <input id="source-topic-labels" v-model="draft.topic_labels" maxlength="1024" autocomplete="off" placeholder="例如：科技, 制造业" />
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="drawer-actions"><button type="button" @click="emit('close')">取消</button><button class="primary" type="submit" :disabled="saving">{{ saving ? "正在提交" : "提交并识别" }}</button></div>
    </form>
  </el-drawer>
</template>

<style scoped>
h2, p { margin-top: 0; } h2 { font-family: "Noto Serif SC", "Songti SC", serif; color: #1b3352; }.source-form { display: grid; gap: .55rem; color: #29435f; }.form-intro { padding: .7rem .85rem; color: #79530e; border-left: 3px solid #d4a449; background: #fff8e9; line-height: 1.55; } label { font-size: .88rem; font-weight: 700; } input { width: 100%; min-height: 2.45rem; box-sizing: border-box; padding: .45rem .6rem; color: #1d2b42; border: 1px solid #b8c7d8; border-radius: .2rem; } input:focus-visible, button:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }.form-error { margin: .4rem 0 0; color: #9b1c1c; }.drawer-actions { display: flex; justify-content: end; gap: .7rem; margin-top: 1rem; }.drawer-actions button { min-height: 2.3rem; padding: .42rem .75rem; color: #1e568c; border: 1px solid #9db5cd; border-radius: .2rem; background: #fff; cursor: pointer; }.drawer-actions .primary { color: #fff; border-color: #113a70; background: #113a70; }.drawer-actions button:disabled { cursor: not-allowed; opacity: .65; }
</style>
