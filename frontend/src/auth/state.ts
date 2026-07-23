import { ref } from "vue";

import { getCurrentUser, logout, type CurrentUser } from "../api/auth";

export const currentUser = ref<CurrentUser | null>(null);
export const currentUserError = ref<unknown | null>(null);

export async function loadCurrentUser(): Promise<CurrentUser> {
  if (currentUser.value !== null) return currentUser.value;
  try {
    const user = await getCurrentUser();
    currentUser.value = user;
    currentUserError.value = null;
    return user;
  } catch (error) {
    currentUserError.value = error;
    throw error;
  }
}

export function clearCurrentUser() {
  currentUser.value = null;
  currentUserError.value = null;
}

export async function signOut(): Promise<void> {
  await logout();
  clearCurrentUser();
}
