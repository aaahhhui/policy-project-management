const publicBusinessMessages: Record<string, string> = {
  policy_not_convertible: "当前政策不满足转项目条件，请刷新政策详情。",
  policy_already_converted: "该政策已转为项目，请打开现有项目。",
  primary_entity_missing: "当前政策缺少主申报企业，暂不能转为项目。",
  project_liaison_required: "请选择项目对接人。",
  project_user_inactive: "所选项目用户已停用，请重新选择。",
  project_write_forbidden: "你没有权限修改这个项目。",
  project_transition_invalid: "当前状态不能执行这次变更。",
  project_correction_invalid: "当前状态不能执行这次更正。",
  project_field_validation_failed: "项目字段填写不符合要求，请检查后重试。",
  project_version_conflict: "项目已被他人更新，请重新加载后再操作。",
  idempotency_key_reused: "该创建请求已被使用，请刷新后重试。",
  rule_weight_total_invalid: "启用的评分条件权重合计必须为 100",
  no_published_evaluation_rule: "请先发布一版评估规则后再创建评估",
  evaluation_cancellation_conflict: "当前评估无法取消，请刷新后重试",
  evaluation_confirmation_conflict: "当前评估状态已变化，请刷新后重试",
  confirmation_reason_required: "修改评估结论时必须说明原因",
  primary_entity_required_for_recommendation: "建议申报时必须选择主营企业",
  primary_entity_not_eligible: "所选企业不在本次评估候选范围内",
  primary_entity_reason_required: "变更主营企业时必须说明原因",
  evaluation_not_confirmed: "请先确认评估结论",
  policy_conclusion_reason_required: "调整结论时必须说明原因",
};

const fallbackMessage = "操作未完成，请稍后重试。";

function detailCode(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== "object") return null;
  const data = (response as { data?: unknown }).data;
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

export function businessErrorMessage(error: unknown, fallback = fallbackMessage): string {
  const code = detailCode(error);
  return code ? publicBusinessMessages[code] ?? fallback : fallback;
}
