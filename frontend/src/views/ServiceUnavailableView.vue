<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();
const retryTarget = computed(() => safeRetryTarget(route.query.retry));

function safeRetryTarget(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/")) return "/";
  if (
    value.startsWith("//") ||
    value.startsWith("/\\") ||
    value === "/login" ||
    value.startsWith("/service-unavailable")
  ) {
    return "/";
  }
  return value;
}

async function retry() {
  await router.push(retryTarget.value);
}
</script>

<template>
  <main class="service-unavailable" aria-labelledby="service-title">
    <section>
      <p class="eyebrow">连接状态</p>
      <h1 id="service-title">服务暂时不可用，请稍后重试</h1>
      <p>系统暂时无法确认会话状态。请稍后刷新页面，或返回登录页重试。</p>
      <div class="actions">
        <button type="button" @click="retry">重试</button>
        <RouterLink to="/login">返回登录</RouterLink>
      </div>
    </section>
  </main>
</template>

<style scoped>
.service-unavailable { min-height: 100vh; display: grid; place-items: center; padding: 2rem; color: #14223a; background: #f7f9fc; }
section { width: min(100%, 34rem); padding: 2.5rem; border: 1px solid #dce5f0; background: #fff; box-shadow: 0 18px 45px rgb(23 52 91 / 10%); }
.eyebrow { margin: 0 0 1rem; color: #2b6c9d; font: 700 0.75rem/1.2 ui-monospace, "Cascadia Mono", monospace; letter-spacing: 0.13em; }
h1 { margin: 0; font: 600 1.75rem/1.35 "Noto Serif SC", "Songti SC", Georgia, serif; }
p { color: #5d6d83; line-height: 1.8; }
.actions { display: flex; align-items: center; gap: 1rem; }
button { min-height: 2.5rem; padding: 0 1rem; color: #fff; border: 1px solid #176898; background: #176898; font-weight: 700; cursor: pointer; }
button:focus-visible, a:focus-visible { outline: 3px solid #e3b260; outline-offset: 2px; }
a { color: #176898; font-weight: 700; }
</style>
