<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import { currentUser, currentUserError, signOut } from "../auth/state";

const router = useRouter();
const canManageSources = computed(() => currentUser.value?.roles.includes("applicant_owner") ?? false);
const logoutError = ref("");

async function handleSignOut() {
  logoutError.value = "";
  try {
    await signOut();
    await router.push("/login");
  } catch {
    logoutError.value = "退出失败，请重试";
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <RouterLink class="brand" to="/">科技政策管理</RouterLink>
      <div class="user-tools">
        <span v-if="currentUser">{{ currentUser.display_name }}</span>
        <span v-else-if="currentUserError">会话状态不可用</span>
        <span v-else>正在加载会话</span>
        <el-button text @click="handleSignOut">退出登录</el-button>
      </div>
    </header>
    <p v-if="logoutError" class="logout-error" role="alert">{{ logoutError }}</p>
    <div class="app-body">
      <nav class="app-nav" aria-label="主导航">
        <RouterLink to="/">工作台</RouterLink>
        <RouterLink v-if="canManageSources" to="/sources">政策来源</RouterLink>
        <RouterLink to="/profile">企业档案</RouterLink>
      </nav>
      <main class="app-content"><RouterView /></main>
    </div>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; color: #1d2b42; background: #f5f8fc; font-family: Inter, "Microsoft YaHei", sans-serif; }
.app-header { display: flex; align-items: center; justify-content: space-between; min-height: 4rem; padding: 0 2rem; color: #fff; background: #113a70; }
.brand { color: inherit; font: 600 1.1rem/1.2 "Noto Serif SC", "Songti SC", serif; text-decoration: none; }
.user-tools { display: flex; align-items: center; gap: 0.8rem; font-size: 0.875rem; }
.user-tools :deep(.el-button) { color: #fff; }
.app-body { display: grid; grid-template-columns: 13rem 1fr; min-height: calc(100vh - 4rem); }
.app-nav { padding: 1.5rem 1rem; border-right: 1px solid #dbe5f0; background: #fff; }
.app-nav a { display: block; margin-bottom: 0.35rem; padding: 0.7rem 0.85rem; color: #455a75; border-left: 3px solid transparent; text-decoration: none; }
.app-nav a.router-link-exact-active { color: #113a70; border-left-color: #e3b260; background: #eef5fa; font-weight: 700; }
.app-content { padding: 2rem; }
.logout-error { margin: 0; padding: 0.6rem 2rem; color: #9b1c1c; background: #fff1f0; font-size: 0.875rem; }
@media (max-width: 720px) { .app-header { padding: 0 1rem; } .app-body { grid-template-columns: 1fr; } .app-nav { display: flex; gap: 0.5rem; padding: 0.5rem 1rem; border-right: 0; border-bottom: 1px solid #dbe5f0; } .app-nav a { margin: 0; } .app-content { padding: 1.25rem; } }
</style>
