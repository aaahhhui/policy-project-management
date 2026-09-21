<script setup lang="ts">
import type { ProfileAuditSummary } from "../../api/profiles";
defineProps<{ audits: ProfileAuditSummary[] }>();
function safeValue(value: unknown): string { if (value === "[redacted]") return "已隐藏"; if (value === undefined || value === null || value === "") return "未提供"; return typeof value === "string" ? value : JSON.stringify(value); }
</script>
<template>
  <section class="profile-audits" aria-label="最近审计">
    <h3>最近审计</h3><p v-if="audits.length === 0">暂无审计记录。</p>
    <ol v-else><li v-for="event in audits" :key="event.id"><p class="audit-heading">{{ event.actor_display_name }} · {{ event.occurred_at }}</p><p class="audit-fields">变更字段：{{ event.changed_fields.join("、") || "未提供" }}</p><ul><li v-for="field in event.changed_fields" :key="field">{{ field }}：{{ safeValue(event.before_values[field]) }} → {{ safeValue(event.after_values[field]) }}</li></ul></li></ol>
  </section>
</template>
<style scoped>
.profile-audits{margin-top:1.25rem;padding-top:1rem;border-top:1px solid #d6e1ec}.profile-audits h3{margin:0 0 .6rem;color:#1b3352;font-family:"Noto Serif SC","Songti SC",serif;font-size:1rem}.profile-audits>p{margin:0;color:#60758d}.profile-audits ol{margin:0;padding-left:1.2rem}.profile-audits ol>li{padding:.45rem 0}.audit-heading,.audit-fields{margin:0;line-height:1.5}.audit-heading{color:#435d78;font-size:.86rem}.audit-fields{margin-top:.2rem;color:#1e568c;font-weight:700;font-size:.86rem}.profile-audits ul{margin:.25rem 0 0;padding-left:1.1rem;color:#526a86;font-size:.86rem;line-height:1.55}
</style>
