<script setup lang="ts">
import { computed, reactive, watch } from "vue";

import type { PolicySource, SourceCreateInput, SourceUpdateInput } from "../../api/sources";

type SourceDraft = SourceCreateInput & { is_enabled: boolean };

const props = defineProps<{
  open: boolean;
  source: PolicySource | null;
  saving?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  save: [payload: SourceCreateInput | SourceUpdateInput];
}>();

const title = computed(() => (props.source ? "编辑政策来源" : "添加政策来源"));
const draft = reactive<SourceDraft>({ name: "", home_url: "", channels: [], is_enabled: true });

function resetDraft() {
  draft.name = props.source?.name ?? "";
  draft.home_url = props.source?.home_url ?? "";
  draft.is_enabled = props.source?.is_enabled ?? true;
  draft.channels = (props.source?.channels ?? []).map(({ code, name, list_url, is_enabled }) => ({
    code,
    name,
    list_url,
    is_enabled,
  }));
}

watch(() => [props.open, props.source] as const, resetDraft, { immediate: true });

function addChannel() {
  draft.channels.push({ code: "", name: "", list_url: "", is_enabled: true });
}

function removeChannel(index: number) {
  draft.channels.splice(index, 1);
}

function submit() {
  const payload: SourceCreateInput = {
    name: draft.name.trim(),
    home_url: draft.home_url.trim(),
    channels: draft.channels.map((channel) => ({
      ...channel,
      code: channel.code.trim(),
      name: channel.name.trim(),
      list_url: channel.list_url.trim(),
    })),
  };
  emit("save", props.source ? { ...payload, is_enabled: draft.is_enabled } : payload);
}
</script>

<template>
  <el-drawer :model-value="open" :append-to-body="true" size="min(42rem, 100%)" @close="emit('close')">
    <template #header><h2>{{ title }}</h2></template>
    <form class="source-form" @submit.prevent="submit">
      <p class="form-intro">新增来源默认为待适配；待适配来源不能采集。</p>
      <label for="source-name">来源名称</label>
      <input id="source-name" v-model="draft.name" required maxlength="255" autocomplete="off" />

      <label for="source-home-url">官网地址</label>
      <input id="source-home-url" v-model="draft.home_url" required type="url" maxlength="2048" placeholder="https://" />

      <label v-if="source" class="check-row" for="source-enabled"><input id="source-enabled" v-model="draft.is_enabled" type="checkbox" /> 启用来源</label>

      <div class="channels-heading">
        <div><h3>采集栏目</h3><p>移除的栏目会停用，不会删除已有采集记录。</p></div>
        <button type="button" class="text-button" aria-label="添加栏目" @click="addChannel">添加栏目</button>
      </div>
      <p v-if="!draft.channels.length" class="empty-channels">尚未添加栏目。</p>
      <fieldset v-for="(channel, index) in draft.channels" :key="index" class="channel-row">
        <legend>栏目 {{ index + 1 }}</legend>
        <label :for="`channel-code-${index}`">代码</label>
        <input :id="`channel-code-${index}`" v-model="channel.code" required maxlength="64" />
        <label :for="`channel-name-${index}`">名称</label>
        <input :id="`channel-name-${index}`" v-model="channel.name" required maxlength="255" />
        <label :for="`channel-url-${index}`">列表地址</label>
        <input :id="`channel-url-${index}`" v-model="channel.list_url" required type="url" maxlength="2048" />
        <label class="check-row"><input v-model="channel.is_enabled" type="checkbox" /> 启用栏目</label>
        <button type="button" class="remove-button" @click="removeChannel(index)">移除栏目</button>
      </fieldset>

      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="drawer-actions">
        <button type="button" @click="emit('close')">取消</button>
        <button class="primary" type="submit" :disabled="saving">{{ saving ? "正在保存" : "保存来源" }}</button>
      </div>
    </form>
  </el-drawer>
</template>

<style scoped>
h2, h3, p { margin-top: 0; }
h2, h3 { font-family: "Noto Serif SC", "Songti SC", serif; color: #1b3352; }
.source-form { display: grid; gap: .55rem; color: #29435f; }
.form-intro { padding: .7rem .85rem; color: #79530e; background: #fff8e9; border-left: 3px solid #d4a449; line-height: 1.55; }
label { font-size: .88rem; font-weight: 700; }
input:not([type="checkbox"]) { width: 100%; min-height: 2.45rem; box-sizing: border-box; padding: .45rem .6rem; color: #1d2b42; border: 1px solid #b8c7d8; border-radius: .2rem; }
input:focus-visible, button:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }
.check-row { display: flex; align-items: center; gap: .45rem; margin: .35rem 0; }
.channels-heading { display: flex; align-items: start; justify-content: space-between; gap: 1rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #d6e1ec; }
.channels-heading h3 { margin-bottom: .25rem; }.channels-heading p, .empty-channels { margin-bottom: 0; color: #60758d; font-size: .86rem; line-height: 1.5; }
.text-button, .remove-button, .drawer-actions button { min-height: 2.3rem; padding: .42rem .75rem; color: #1e568c; border: 1px solid #9db5cd; border-radius: .2rem; background: #fff; cursor: pointer; }
.channel-row { display: grid; gap: .45rem; margin: .25rem 0; padding: .85rem; border: 1px solid #d6e1ec; }.channel-row legend { padding: 0 .3rem; color: #526a86; font-size: .85rem; font-weight: 700; }
.remove-button { justify-self: start; color: #9b1c1c; border-color: #e6b7b5; }.form-error { margin: .4rem 0 0; color: #9b1c1c; }.drawer-actions { display: flex; justify-content: end; gap: .7rem; margin-top: 1rem; }.drawer-actions .primary { color: #fff; border-color: #113a70; background: #113a70; }.drawer-actions button:disabled { cursor: not-allowed; opacity: .65; }
</style>
