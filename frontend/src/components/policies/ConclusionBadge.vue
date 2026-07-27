<script setup lang="ts">
const props = defineProps<{ conclusion: string; confirmed: boolean }>();
const labels: Record<string, string> = {
  pending_confirmation: "待确认", recommend_apply: "建议申报", watch: "持续关注",
  not_recommended: "暂不建议申报", uncertain: "无法判断",
};
</script>

<template>
  <span data-conclusion :class="['conclusion-badge', { weak: !props.confirmed }]">
    {{ labels[props.conclusion] ?? props.conclusion }}
  </span>
</template>

<style scoped>
.conclusion-badge { display: inline-flex; padding: .28rem .7rem; color: #113a70; border: 1px solid #113a70; border-radius: 99px; background: #eef5fa; font-size: .82rem; font-weight: 800; white-space: nowrap; }
.conclusion-badge.weak { color: #60758d; border-style: dashed; border-color: #8fa3b8; background: #f7f9fb; }
</style>
