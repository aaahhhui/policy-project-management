import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import EvaluationSummary from "../../src/components/evaluations/EvaluationSummary.vue";
import ConclusionBadge from "../../src/components/policies/ConclusionBadge.vue";

const succeededEvaluation = {
  id: 31,
  policy_version_id: 12,
  status: "succeeded",
  prompt_version: "stage1-v1",
  adapter_key: "mock",
  model_name: null,
  profile_snapshot: [],
  summary: "政策方向与公司数字化仿真能力匹配。",
  key_conditions: ["申报主体须在广东省内开展项目", "项目须在申报期内启动"],
  conclusion: "recommend_apply",
  error_message: null,
  started_at: "2026-07-28T01:00:00Z",
  finished_at: "2026-07-28T01:00:05Z",
  created_at: "2026-07-28T01:00:00Z",
  entities: [
    {
      entity_seed_code: "ENTITY-BEIJING",
      match_level: "high",
      evidence: ["具备数字孪生研发能力"],
      unmet_conditions: ["需确认项目实施地点"],
      risks: [],
      recommended_action: "核对广东项目主体资格",
    },
    {
      entity_seed_code: "ENTITY-SUZHOU",
      match_level: "medium",
      evidence: ["具备工业软件产品"],
      unmet_conditions: [],
      risks: ["研发数据仍需补充"],
      recommended_action: "补充研发投入证明",
    },
    {
      entity_seed_code: "ENTITY-SHENZHEN",
      match_level: "uncertain",
      evidence: ["业务方向与政策一致"],
      unmet_conditions: [],
      risks: ["法人主体类型待核验"],
      recommended_action: "先核验法人主体类型",
    },
  ],
};

describe("EvaluationSummary", () => {
  it("shows one weak AI conclusion and all three entity results", () => {
    const wrapper = mount({
      components: { ConclusionBadge, EvaluationSummary },
      data: () => ({ evaluation: succeededEvaluation }),
      template: `
        <div>
          <ConclusionBadge conclusion="recommend_apply" :confirmed="false" />
          <EvaluationSummary :evaluation="evaluation" />
        </div>
      `,
    });

    expect(wrapper.findAll("[data-conclusion]")).toHaveLength(1);
    expect(wrapper.get("[data-conclusion]").text()).toBe("建议申报");
    expect(wrapper.get("[data-conclusion]").classes()).toContain("weak");
    expect(wrapper.text()).toContain("北京适创科技有限公司");
    expect(wrapper.text()).toContain("苏州数算软云科技有限公司");
    expect(wrapper.text()).toContain("深圳适创腾扬科技有限公司");
    expect(wrapper.text()).toContain("具备数字孪生研发能力");
    expect(wrapper.text()).toContain("需确认项目实施地点");
    expect(wrapper.text()).toContain("法人主体类型待核验");
    expect(wrapper.text()).toContain("先核验法人主体类型");
    expect(wrapper.text()).toContain("批次 #31");
  });
});
