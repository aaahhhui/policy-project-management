<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { getPolicy, getPolicyVersions, type PolicyDetail, type PolicyVersion } from "../api/policies";
import AttachmentList from "../components/policies/AttachmentList.vue";
import ConclusionBadge from "../components/policies/ConclusionBadge.vue";
import VersionHistory from "../components/policies/VersionHistory.vue";

const route = useRoute();
const policy = ref<PolicyDetail | null>(null);
const versions = ref<PolicyVersion[]>([]);
const loading = ref(true);
const error = ref("");
function formatDate(value: string | null) { return value ?? "未注明"; }
function formatTime(value: string) { return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
onMounted(async () => {
  const id = Number(route.params.id);
  try { [policy.value, versions.value] = await Promise.all([getPolicy(id), getPolicyVersions(id)]); }
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
    <VersionHistory :versions="versions" />
    <section class="evaluation-reserved" aria-label="评估区域"><h2>企业匹配评估</h2><p>评估结果将在后台任务完成后显示。</p></section>
  </article>
</template>

<style scoped>
.policy-detail { max-width: 68rem; margin: 0 auto; color: #1b3352; }.policy-title { display: flex; align-items: start; justify-content: space-between; gap: 2rem; padding-bottom: 1.35rem; border-bottom: 3px solid #1e568c; }.eyebrow { margin: 0 0 .45rem; color: #6a7e95; font-size: .75rem; font-weight: 800; letter-spacing: .09em; }.policy-title h1 { max-width: 48rem; margin: 0; font: 700 clamp(1.8rem, 4vw, 2.65rem)/1.25 "Noto Serif SC", "Songti SC", serif; }.policy-title p:last-child { color: #60758d; }.facts, .document, .files, .evaluation-reserved, :deep(section) { margin-top: 1.5rem; padding: 1.2rem 1.35rem; border: 1px solid #d8e2ec; background: #fff; }.facts dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 0 0 1rem; }.facts dl div { padding-left: .75rem; border-left: 3px solid #d3a747; }.facts dt { color: #6a7e95; font-size: .75rem; }.facts dd { margin: .3rem 0 0; font-weight: 700; }.facts ul { margin: 0; padding: 0; list-style: none; }.facts li { display: flex; justify-content: space-between; gap: 1rem; padding-top: .8rem; border-top: 1px solid #e3ebf3; }.facts a, .snapshot { color: #14558c; }.document h2, .files > h2, .evaluation-reserved h2 { margin-top: 0; font: 700 1.2rem/1.4 "Noto Serif SC", "Songti SC", serif; }.body-text { color: #293f58; line-height: 1.9; white-space: pre-wrap; }.evaluation-reserved { border-style: dashed; color: #657a91; }.error { padding: 1rem; color: #9b1c1c; background: #fff1f0; }@media (max-width: 700px) { .policy-title { flex-direction: column; }.facts dl { grid-template-columns: 1fr; }.facts li { align-items: start; flex-direction: column; } }
</style>
