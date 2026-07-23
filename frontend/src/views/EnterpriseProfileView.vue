<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  getBusinessEntities,
  getSharedProfile,
  type BusinessEntityResponse,
  type ProfileResponse,
} from "../api/profiles";
import VerificationBadge from "../components/VerificationBadge.vue";

const sharedProfile = ref<ProfileResponse | null>(null);
const entities = ref<BusinessEntityResponse[]>([]);
const loading = ref(true);
const loadError = ref("");

const expectedEntities = [
  { seedCode: "ENTITY-BEIJING", city: "北京" },
  { seedCode: "ENTITY-SUZHOU", city: "苏州" },
  { seedCode: "ENTITY-SHENZHEN", city: "深圳" },
] as const;

const orderedEntities = computed(() => {
  const entitiesBySeedCode = new Map(entities.value.map((entity) => [entity.seed_code, entity]));
  return expectedEntities.flatMap(({ seedCode }) => {
    const entity = entitiesBySeedCode.get(seedCode);
    return entity ? [entity] : [];
  });
});

const missingCities = computed(() =>
  expectedEntities
    .filter(({ seedCode }) => !entities.value.some((entity) => entity.seed_code === seedCode))
    .map(({ city }) => city),
);

const entityImportState = computed(() => {
  if (orderedEntities.value.length === 0) return "empty";
  return missingCities.value.length > 0 ? "partial" : "complete";
});

const sharedFields = computed(() => {
  if (!sharedProfile.value) return [];
  const data = sharedProfile.value.data;
  return [
    ["所属行业", joinValues(data.industries)],
    ["业务方向", joinValues(data.business_directions)],
    ["技术能力", joinValues(data.technical_capabilities)],
    ["产品", joinValues(data.products)],
    ["联系方式", [data.contact_phone, data.contact_email].filter(Boolean).join(" · ")],
  ].filter(([, value]) => value);
});

function joinValues(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value.filter((item): item is string => typeof item === "string").join("、");
}

function stringValue(data: Record<string, unknown>, key: string): string {
  const value = data[key];
  return typeof value === "string" ? value : "未提供";
}

function regionValue(data: Record<string, unknown>): string {
  const region = data.registered_region;
  if (typeof region !== "object" || region === null) return "未提供";
  return (
    Object.values(region)
      .filter((value): value is string => typeof value === "string")
      .join(" ") || "未提供"
  );
}

function candidateCapital(data: Record<string, unknown>): string {
  const capital = data.registered_capital_candidate;
  if (typeof capital !== "object" || capital === null || !("amount" in capital)) return "";
  const unit = "unit" in capital && typeof capital.unit === "string" ? capital.unit : "";
  return `候选注册资本：${String(capital.amount)}${unit}`;
}

async function loadProfile() {
  loading.value = true;
  loadError.value = "";
  try {
    const [profile, businessEntities] = await Promise.all([getSharedProfile(), getBusinessEntities()]);
    sharedProfile.value = profile;
    entities.value = businessEntities;
  } catch {
    loadError.value = "企业档案暂时无法加载，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

onMounted(loadProfile);
</script>

<template>
  <section class="profile-page" aria-labelledby="profile-title">
    <header class="page-heading">
      <p class="eyebrow">企业基础信息 · 只读</p>
      <h1 id="profile-title">企业档案</h1>
      <p>信息保留其来源核验状态；候选与待核验信息不会作为已确认事实使用。</p>
    </header>

    <p v-if="loading" class="status-message" role="status">正在加载企业档案…</p>
    <p v-else-if="loadError" class="status-message status-message--error" role="alert">{{ loadError }}</p>

    <template v-else-if="sharedProfile">
      <section class="shared-profile" aria-labelledby="shared-profile-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">公司共享档案</p>
            <h2 id="shared-profile-title">{{ sharedProfile.display_name }}</h2>
          </div>
          <VerificationBadge :status="sharedProfile.verification_status" />
        </div>
        <dl class="field-grid">
          <template v-for="[label, value] in sharedFields" :key="label">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </template>
        </dl>
      </section>

      <section class="entities" aria-labelledby="entities-title">
        <div class="entities-heading">
          <p class="eyebrow">登记主体</p>
          <h2 id="entities-title">企业主体</h2>
        </div>
        <p v-if="entityImportState === 'empty'" class="entity-import-alert" role="alert">
          企业主体种子数据尚未导入。请导入企业档案种子数据后重试。
        </p>
        <p v-else-if="entityImportState === 'partial'" class="entity-import-alert" role="alert">
          企业主体数据不完整，缺少：{{ missingCities.join("、") }}。当前仅显示已导入主体。请联系管理员完成种子导入后刷新重试。
        </p>
        <article v-for="entity in orderedEntities" :key="entity.seed_code" class="entity-card">
          <div class="section-heading">
            <div>
              <p class="entity-code">{{ entity.seed_code }}</p>
              <h3>{{ entity.legal_name }}</h3>
            </div>
            <VerificationBadge :status="entity.verification_status" />
          </div>
          <dl class="entity-fields">
            <div>
              <dt>登记地区</dt>
              <dd>{{ regionValue(entity.data) }}</dd>
            </div>
            <div>
              <dt>统一社会信用代码</dt>
              <dd>{{ stringValue(entity.data, "unified_social_credit_code") }}</dd>
            </div>
            <div>
              <dt>办公地址</dt>
              <dd>{{ stringValue(entity.data, "office_address") }}</dd>
            </div>
          </dl>
          <p v-if="candidateCapital(entity.data)" class="candidate-note">{{ candidateCapital(entity.data) }}</p>
        </article>
      </section>
    </template>
  </section>
</template>

<style scoped>
.profile-page { max-width: 74rem; margin: 0 auto; color: #1b3352; }
.page-heading { margin-bottom: 1.75rem; padding: 0 0 1.2rem; border-bottom: 2px solid #1e568c; }
.eyebrow, .entity-code { margin: 0 0 0.4rem; color: #6a7e95; font-size: 0.76rem; font-weight: 800; letter-spacing: 0.09em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; }
h1, h2, h3 { font-family: "Noto Serif SC", "Songti SC", serif; }
h1 { margin-bottom: 0.55rem; font-size: clamp(1.75rem, 3vw, 2.45rem); }
h2 { margin-bottom: 0; font-size: 1.45rem; }
h3 { margin-bottom: 0; font-size: 1.14rem; }
.page-heading > p:last-child { max-width: 52rem; margin-bottom: 0; color: #526a86; line-height: 1.7; }
.shared-profile, .entity-card { background: #fff; border: 1px solid #d6e1ec; box-shadow: 0 0.4rem 1rem rgb(25 58 94 / 6%); }
.shared-profile { padding: clamp(1.1rem, 3vw, 2rem); border-top: 4px solid #d4a449; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.field-grid { display: grid; grid-template-columns: minmax(7.5rem, 0.24fr) 1fr; gap: 0.85rem 1.3rem; margin: 1.6rem 0 0; }
dt { color: #60758d; font-size: 0.86rem; font-weight: 700; }
dd { margin: 0; color: #233f60; line-height: 1.6; }
.entities { margin-top: 2.5rem; }
.entities-heading { margin-bottom: 1rem; }
.entity-card { margin-bottom: 1rem; padding: clamp(1.1rem, 2.5vw, 1.6rem); }
.entity-import-alert { margin: 0 0 1rem; padding: 0.8rem 1rem; color: #874a08; background: #fff8e9; border-left: 3px solid #d4a449; line-height: 1.6; }
.entity-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.35rem 0 0; }
.entity-fields div { min-width: 0; }
.entity-fields dd { overflow-wrap: anywhere; }
.candidate-note { margin: 1.25rem 0 0; padding: 0.7rem 0.85rem; color: #874a08; background: #fff8e9; border-left: 3px solid #d4a449; font-size: 0.9rem; line-height: 1.5; }
.status-message { padding: 1rem; color: #526a86; background: #fff; border: 1px solid #d6e1ec; }
.status-message--error { color: #9b1c1c; background: #fff1f0; border-color: #f1b8b5; }
@media (max-width: 720px) { .section-heading { align-items: flex-start; flex-direction: column; } .field-grid { grid-template-columns: 1fr; gap: 0.3rem; } .field-grid dd { margin-bottom: 0.75rem; } .entity-fields { grid-template-columns: 1fr; gap: 0.75rem; } }
</style>
