import { defineComponent, nextTick, ref, type Ref } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useEvaluationPolling } from "../../src/composables/useEvaluationPolling";

function mountPolling(load: () => Promise<void>, active: Ref<boolean>, intervalMs = 3_000) {
  return mount(defineComponent({
    setup() {
      useEvaluationPolling(load, active, intervalMs);
      return () => null;
    },
  }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useEvaluationPolling", () => {
  it("loads on each interval only while an evaluation is active", async () => {
    vi.useFakeTimers();
    const load = vi.fn().mockResolvedValue(undefined);
    const active = ref(true);
    const wrapper = mountPolling(load, active);

    await vi.advanceTimersByTimeAsync(3_000);
    expect(load).toHaveBeenCalledTimes(1);

    active.value = false;
    await nextTick();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(load).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("does not start a second load before the previous one settles", async () => {
    vi.useFakeTimers();
    let resolveLoad!: () => void;
    const load = vi.fn(() => new Promise<void>((resolve) => { resolveLoad = resolve; }));
    const wrapper = mountPolling(load, ref(true), 3_000);

    await vi.advanceTimersByTimeAsync(3_000);
    await vi.advanceTimersByTimeAsync(9_000);
    expect(load).toHaveBeenCalledTimes(1);

    resolveLoad();
    await vi.runOnlyPendingTimersAsync();
    expect(load).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("does not reschedule after an in-flight load becomes inactive", async () => {
    vi.useFakeTimers();
    let resolveLoad!: () => void;
    const load = vi.fn(() => new Promise<void>((resolve) => { resolveLoad = resolve; }));
    const active = ref(true);
    const wrapper = mountPolling(load, active, 3_000);

    await vi.advanceTimersByTimeAsync(3_000);
    active.value = false;
    await nextTick();
    resolveLoad();
    await vi.advanceTimersByTimeAsync(6_000);

    expect(load).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("retries on the next interval after a failed load", async () => {
    vi.useFakeTimers();
    const load = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(undefined);
    const wrapper = mountPolling(load, ref(true), 3_000);

    await vi.advanceTimersByTimeAsync(3_000);
    await vi.advanceTimersByTimeAsync(3_000);

    expect(load).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("clears its scheduled poll when the view unmounts", async () => {
    vi.useFakeTimers();
    const load = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountPolling(load, ref(true), 3_000);

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(6_000);

    expect(load).not.toHaveBeenCalled();
  });
});
