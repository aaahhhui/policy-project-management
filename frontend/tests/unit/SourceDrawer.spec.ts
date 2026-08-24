import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { describe, expect, it } from "vitest";

import SourceDrawer from "../../src/components/sources/SourceDrawer.vue";

describe("SourceDrawer", () => {
  it("collects a name, public entry URL, and normalized optional labels without technical source inputs", async () => {
    const wrapper = mount(SourceDrawer, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDrawer: { template: "<div><slot name='header' /><slot /></div>" } } } });
    expect(wrapper.get("label[for='source-name']").text()).toContain("来源名称");
    expect(wrapper.get("label[for='source-entry-url']").text()).toContain("公开入口 URL");
    expect(wrapper.get("label[for='source-region-labels']").text()).toContain("地区标签");
    expect(wrapper.get("label[for='source-topic-labels']").text()).toContain("主题标签");
    for (const forbidden of ["栏目", "适配器", "选择器", "XPath", "CSS", "请求头", "凭据", "原始预览"]) expect(wrapper.text()).not.toContain(forbidden);
    await wrapper.get("#source-name").setValue(" 广东科技 "); await wrapper.get("#source-entry-url").setValue(" https://public.example/feed ");
    await wrapper.get("#source-region-labels").setValue("粤A, 粤B,粤A, 粤C,粤D,粤E,粤F,粤G,粤H,粤I,粤J,粤K,粤L,粤M,粤N,粤O,粤P,粤Q,粤R,粤S,粤T,粤U");
    await wrapper.get("#source-topic-labels").setValue(" 科技, 制造业,科技 "); await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("save")?.[0]).toEqual([{ name: "广东科技", entry_url: "https://public.example/feed", region_labels: ["粤A", "粤B", "粤C", "粤D", "粤E", "粤F", "粤G", "粤H", "粤I", "粤J", "粤K", "粤L", "粤M", "粤N", "粤O", "粤P", "粤Q", "粤R", "粤S", "粤T"], topic_labels: ["科技", "制造业"] }]);
  });
});
