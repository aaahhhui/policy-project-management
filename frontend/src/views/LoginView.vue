<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { isUnauthorizedError, login } from "../api/auth";
import { clearCurrentUser } from "../auth/state";

const router = useRouter();
const route = useRoute();
const form = reactive({ login_name: "", password: "" });
const loading = ref(false);
const error = ref("");

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    await login(form);
    clearCurrentUser();
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.push(redirect);
  } catch (requestError) {
    error.value = isUnauthorizedError(requestError)
      ? "账号或密码错误"
      : "服务暂时不可用，请稍后重试";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-introduction" aria-labelledby="platform-title">
      <p class="eyebrow">企业政策运营平台</p>
      <h1 id="platform-title">科技政策管理</h1>
      <p class="introduction-copy">安全访问政策来源、申报事项与企业材料。</p>
      <div class="policy-rule" aria-hidden="true"><span>POLICY / ACCESS</span></div>
    </section>
    <section class="login-panel" aria-labelledby="login-title">
      <div class="login-card">
        <p class="form-kicker">安全登录</p>
        <h2 id="login-title">登录工作台</h2>
        <p class="form-help">请使用已分配的账号登录。</p>
        <el-form @submit.prevent="submit">
          <el-form-item label="账号">
            <el-input v-model.trim="form.login_name" autocomplete="username" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="current-password"
              show-password
            />
          </el-form-item>
          <el-alert v-if="error" :title="error" type="error" :closable="false" />
          <el-button type="primary" native-type="submit" :loading="loading">登录</el-button>
        </el-form>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(280px, 1fr) minmax(420px, 1fr); background: #f7f9fc; color: #14223a; }
.login-introduction { display: flex; flex-direction: column; justify-content: center; padding: clamp(3rem, 9vw, 9rem); color: #f6f9ff; background: #113a70; }
.eyebrow, .form-kicker { margin: 0 0 1rem; color: #75b8d6; font: 700 0.75rem/1.2 ui-monospace, "Cascadia Mono", monospace; letter-spacing: 0.13em; }
h1, h2 { margin: 0; font-family: "Noto Serif SC", "Songti SC", Georgia, serif; font-weight: 600; }
h1 { max-width: 7em; font-size: clamp(2.25rem, 4vw, 4.5rem); line-height: 1.16; letter-spacing: 0.03em; }
.introduction-copy { max-width: 21rem; margin: 1.75rem 0 3.5rem; color: #d5e5f1; font-size: 1rem; line-height: 1.8; }
.policy-rule { display: flex; align-items: center; gap: 1rem; color: #83c1da; font: 600 0.69rem/1 ui-monospace, "Cascadia Mono", monospace; letter-spacing: 0.12em; }
.policy-rule::before { width: 3rem; height: 2px; background: #e3b260; content: ""; }
.login-panel { display: grid; place-items: center; padding: 2rem; }
.login-card { width: min(100%, 27rem); padding: clamp(1.5rem, 4vw, 3rem); background: #fff; border: 1px solid #dce5f0; box-shadow: 0 18px 45px rgb(23 52 91 / 10%); }
.form-kicker { margin-bottom: 0.65rem; color: #2b6c9d; }
h2 { font-size: 1.75rem; line-height: 1.3; }
.form-help { margin: 0.65rem 0 2rem; color: #5d6d83; font-size: 0.9rem; }
.login-card :deep(.el-form-item__label) { color: #263b57; font-weight: 600; }
.login-card :deep(.el-input__wrapper) { min-height: 2.75rem; box-shadow: 0 0 0 1px #b9c8d8 inset; }
.login-card :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px #176898 inset; }
.login-card :deep(.el-alert) { margin-bottom: 1rem; }
.login-card :deep(.el-button) { width: 100%; min-height: 2.8rem; margin-top: 0.5rem; background: #176898; border-color: #176898; font-weight: 700; }
.login-card :deep(.el-button:hover) { background: #0f527d; border-color: #0f527d; }
.login-card :deep(button:focus-visible), .login-card :deep(input:focus-visible) { outline: 3px solid #e3b260; outline-offset: 2px; }
@media (max-width: 720px) { .login-page { grid-template-columns: 1fr; } .login-introduction { min-height: 12rem; padding: 2rem; } h1 { font-size: 2rem; } .introduction-copy, .policy-rule { display: none; } .login-panel { align-items: start; padding: 1.25rem; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; } }
</style>
