<script setup lang="ts">
import { reactive, watch } from "vue";

import type { ProjectStatus } from "../../api/projects";
import type { ProjectLedgerFilters } from "./projectFilters";

const pageSizes = [10, 20, 50] as const;
const statuses: Array<{ value: ProjectStatus; label: string }> = [
  { value: "pending_application", label: "待申报" },
  { value: "submitted", label: "已提交" },
  { value: "succeeded", label: "已成功" },
  { value: "rejected", label: "未获批" },
  { value: "terminated", label: "已终止" },
];

const props = defineProps<{ filters: ProjectLedgerFilters }>();
const emit = defineEmits<{ apply: [filters: ProjectLedgerFilters] }>();
const draft = reactive<ProjectLedgerFilters>({ ...props.filters });

function apply(): void {
  emit("apply", { ...draft, page: 1 });
}

watch(() => props.filters, (filters) => Object.assign(draft, filters), { deep: true });
</script>

<template>
  <form class="project-filters" @submit.prevent="apply">
    <label>关键词<input v-model="draft.q" aria-label="搜索项目" placeholder="项目或政策名称" /></label>
    <label>企业编码<input v-model="draft.primary_entity_seed_code" aria-label="企业编码" /></label>
    <label>对接人编号<input v-model="draft.liaison_id" aria-label="对接人编号" inputmode="numeric" /></label>
    <label>项目状态
      <select v-model="draft.status" aria-label="项目状态"><option value="">全部状态</option><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select>
    </label>
    <label>截止起始<input v-model="draft.deadline_from" type="date" /></label>
    <label>截止结束<input v-model="draft.deadline_to" type="date" /></label>
    <label class="mine"><input v-model="draft.mine" type="checkbox" /> 仅我的项目</label>
    <label>每页项目数
      <select v-model.number="draft.page_size" aria-label="每页项目数"><option v-for="size in pageSizes" :key="size" :value="size">{{ size }}</option></select>
    </label>
    <button type="submit">筛选</button>
  </form>
</template>

<style scoped>
.project-filters { display: grid; grid-template-columns: repeat(4, minmax(9rem, 1fr)); gap: .7rem; align-items: end; padding: .9rem; border: 1px solid #d8e2ec; background: #fff; }.project-filters label { display: grid; gap: .3rem; color: #5c7188; font-size: .75rem; font-weight: 700; }.project-filters input:not([type="checkbox"]), .project-filters select { box-sizing: border-box; width: 100%; min-height: 2.35rem; padding: .35rem .55rem; border: 1px solid #aebfd0; background: #fff; }.project-filters .mine { display: flex; align-items: center; min-height: 2.35rem; gap: .4rem; }.project-filters button { min-height: 2.35rem; color: #fff; border: 1px solid #113a70; background: #113a70; font: inherit; font-weight: 800; cursor: pointer; } input:focus-visible, select:focus-visible, button:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; } @media (max-width: 900px) { .project-filters { grid-template-columns: 1fr 1fr; } } @media (max-width: 560px) { .project-filters { grid-template-columns: 1fr; } }
</style>
