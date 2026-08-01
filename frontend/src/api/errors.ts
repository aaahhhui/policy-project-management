const publicBusinessMessages: Record<string, string> = {
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
