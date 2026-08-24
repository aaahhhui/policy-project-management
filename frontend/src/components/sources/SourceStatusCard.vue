<script setup lang="ts">
import { computed, ref } from "vue";
import type { PolicySource } from "../../api/sources";

const props = defineProps<{ source: PolicySource; canWrite: boolean; busy?: boolean }>();
const emit = defineEmits<{ retry: [id: number, version: number, representativeUrl?: string]; enable: [id: number, version: number]; disable: [id: number, version: number] }>();
const statusLabel = computed(() => ({ recognizing: "识别中", ready_to_enable: "可启用", enabled: "已启用", pending_verification: "待人工确认", rejected: "无法使用", disabled: "已停用" })[props.source.recognition_status]);
const nextStep = computed(() => ({ recognizing: "系统正在识别公开入口，请稍后查看。", ready_to_enable: "预览已就绪，请确认后启用采集。", enabled: "此来源会按既有计划采集。", pending_verification: "可重新识别公开入口。", rejected: "请修正公开入口后重新识别。", disabled: "已停止采集，历史记录保留。" })[props.source.recognition_status]);
const representativeUrl = ref("");
const retryError = ref("");
const canRetry = computed(() => props.source.recognition_status === "pending_verification" || props.source.recognition_status === "rejected");
const safeEntryUrl = computed(() => safeHttpUrl(props.source.entry_url));
function formatTime(value: string | null) { return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "尚无记录"; }
function safeHttpUrl(value: string): string | null {
  const trimmed = value.trim();
  try {
    const protocol = new URL(trimmed).protocol;
    return protocol === "http:" || protocol === "https:" ? trimmed : null;
  } catch { return null; }
}
function retry() {
  const value = representativeUrl.value.trim();
  if (value && !safeHttpUrl(value)) {
    retryError.value = "请输入以 http:// 或 https:// 开头的公开政策链接。";
    return;
  }
  retryError.value = "";
  if (value) emit("retry", props.source.id, props.source.version, value);
  else emit("retry", props.source.id, props.source.version);
}
function clearRepresentativeUrl() { representativeUrl.value = ""; retryError.value = ""; }
</script>

<template>
  <article :class="['source-card', `source-card--${source.recognition_status}`]">
    <header class="source-card__heading"><div><p class="source-card__status">{{ statusLabel }}</p><h2>{{ source.name }}</h2></div><a v-if="safeEntryUrl" :href="safeEntryUrl" target="_blank" rel="noreferrer">查看公开入口</a><span v-else class="source-card__entry-invalid">公开入口不可用</span></header>
    <p v-if="source.region_labels.length || source.topic_labels.length" class="source-card__labels"><span v-for="label in source.region_labels" :key="`region-${label}`">{{ label }}</span><span v-for="label in source.topic_labels" :key="`topic-${label}`">{{ label }}</span></p>
    <p class="source-card__preview">预览：{{ source.recognition_summary || "暂无安全预览" }}</p><p class="source-card__next">{{ nextStep }}</p>
    <dl class="source-card__history"><div><dt>最近采集</dt><dd>{{ formatTime(source.latest_collection_at) }}</dd></div><div><dt>最近结果</dt><dd>{{ source.latest_result ?? "尚无结果" }}</dd></div></dl>
    <div v-if="canWrite" class="source-card__actions"><button v-if="source.recognition_status === 'ready_to_enable'" type="button" :aria-label="`启用 ${source.name}`" :disabled="busy" @click="emit('enable', source.id, source.version)">启用</button><button v-else-if="source.recognition_status === 'enabled'" type="button" :aria-label="`停用 ${source.name}`" :disabled="busy" @click="emit('disable', source.id, source.version)">停用</button><form v-else-if="canRetry" class="source-card__retry-form" @submit.prevent="retry"><label :for="`representative-url-${source.id}`">代表性公开政策链接（可选）</label><input :id="`representative-url-${source.id}`" v-model="representativeUrl" :aria-label="`代表性公开政策链接 ${source.name}`" type="url" maxlength="2048" autocomplete="off" placeholder="https://" :disabled="busy" /><p>可补充一条公开政策链接帮助识别；留空则直接重新识别。</p><p v-if="retryError" role="alert">{{ retryError }}</p><div><button type="submit" :aria-label="`重新识别 ${source.name}`" :disabled="busy">重新识别</button><button v-if="representativeUrl" type="button" :aria-label="`取消补充链接 ${source.name}`" :disabled="busy" @click="clearRepresentativeUrl">取消补充链接</button></div></form></div>
  </article>
</template>

<style scoped>
.source-card { padding: 1rem 1.1rem; border: 1px solid #d6e1ec; border-left: 4px solid #8ea6bc; background: #fff; box-shadow: 0 .3rem .8rem rgb(25 58 94 / 5%); }.source-card--ready_to_enable, .source-card--enabled { border-left-color: #24764a; }.source-card--pending_verification { border-left-color: #d4a449; }.source-card--rejected { border-left-color: #b43c36; }.source-card--disabled { border-left-color: #77899c; }.source-card__heading { display: flex; align-items: start; justify-content: space-between; gap: 1rem; }.source-card__heading h2 { margin: .12rem 0 0; color: #1b3352; font-family: "Noto Serif SC", "Songti SC", serif; font-size: 1.15rem; }.source-card__heading a { color: #1e568c; font-size: .85rem; white-space: nowrap; }.source-card__entry-invalid { color: #79530e; font-size: .85rem; }.source-card__status { margin: 0; color: #526a86; font-size: .8rem; font-weight: 800; letter-spacing: .06em; }.source-card__labels { display: flex; flex-wrap: wrap; gap: .35rem; margin: .8rem 0 0; }.source-card__labels span { padding: .14rem .45rem; color: #526a86; background: #eef5fa; font-size: .78rem; }.source-card__preview { margin: .85rem 0 .35rem; color: #29435f; line-height: 1.6; }.source-card__next { margin: 0; color: #526a86; font-size: .88rem; line-height: 1.55; }.source-card__history { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; margin: .95rem 0 0; padding-top: .8rem; border-top: 1px solid #e3ebf3; }.source-card__history div { min-width: 0; }.source-card__history dt { color: #6a7e95; font-size: .76rem; font-weight: 700; }.source-card__history dd { margin: .2rem 0 0; color: #29435f; font-size: .86rem; overflow-wrap: anywhere; }.source-card__actions { margin-top: .95rem; }.source-card__actions button { min-height: 2.3rem; padding: .42rem .75rem; color: #fff; border: 1px solid #113a70; border-radius: .2rem; background: #113a70; cursor: pointer; }.source-card__actions button:disabled, .source-card__retry-form input:disabled { cursor: not-allowed; opacity: .65; }.source-card__actions button:focus-visible, .source-card__heading a:focus-visible, .source-card__retry-form input:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }.source-card__retry-form { display: grid; gap: .4rem; }.source-card__retry-form label { color: #29435f; font-size: .84rem; font-weight: 700; }.source-card__retry-form input { min-height: 2.3rem; padding: .42rem .55rem; color: #1d2b42; border: 1px solid #b8c7d8; border-radius: .2rem; }.source-card__retry-form p { margin: 0; color: #526a86; font-size: .8rem; line-height: 1.45; }.source-card__retry-form p[role="alert"] { color: #9b1c1c; }.source-card__retry-form div { display: flex; flex-wrap: wrap; gap: .45rem; } @media (max-width: 720px) { .source-card__heading { display: grid; gap: .4rem; }.source-card__history { grid-template-columns: 1fr; } }
</style>
