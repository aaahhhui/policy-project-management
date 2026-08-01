import { onUnmounted, toValue, watch, type WatchSource } from "vue";

export function useEvaluationPolling(
  load: () => Promise<unknown>,
  isActive: WatchSource<boolean>,
  intervalMs = 3_000,
): void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let loading = false;
  let disposed = false;

  function clearTimer(): void {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule(): void {
    if (disposed || loading || timer !== null) return;
    timer = setTimeout(async () => {
      timer = null;
      if (disposed || !toValue(isActive)) return;
      loading = true;
      try {
        await load();
      } catch {
        // The next scheduled cycle retries failed refreshes.
      } finally {
        loading = false;
        if (!disposed && toValue(isActive)) schedule();
      }
    }, intervalMs);
  }

  watch(isActive, (active) => {
    if (active) schedule();
    else clearTimer();
  }, { immediate: true });

  onUnmounted(() => {
    disposed = true;
    clearTimer();
  });
}
