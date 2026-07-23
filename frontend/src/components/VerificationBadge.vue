<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status: string }>();

const labels: Record<string, string> = {
  public_verified: "公开信息已核验",
  pending_business_license_review: "待营业执照核验",
  candidate_pending_business_license_review: "候选信息，待核验",
  historical_public_record_pending_current_certificate: "历史公开记录，待核验现状",
};

const label = computed(() => labels[props.status] ?? "待核验");
const tone = computed(() => (props.status === "public_verified" ? "verified" : "pending"));
const accessibleStatus = computed(() => `${label.value}：${props.status}`);
</script>

<template>
  <span
    class="verification-badge"
    :class="`verification-badge--${tone}`"
    :title="status"
    :aria-label="accessibleStatus"
    tabindex="0"
  >
    {{ label }}
  </span>
</template>

<style scoped>
.verification-badge { display: inline-flex; align-items: center; min-height: 1.8rem; padding: 0.15rem 0.55rem; border: 1px solid transparent; border-radius: 999px; font-size: 0.75rem; font-weight: 700; line-height: 1.35; }
.verification-badge--verified { color: #155e3b; background: #e8f5ed; border-color: #9bcaaa; }
.verification-badge--pending { color: #874a08; background: #fff5df; border-color: #e6be75; }
.verification-badge:focus-visible { outline: 3px solid #1e568c; outline-offset: 2px; }
</style>
