import http from "./http";

export type RuleVersionStatus = "draft" | "published" | "retired";

export interface HardRule {
  code: string;
  name: string;
  instruction: string;
  enabled: boolean;
}

export interface WeightedRule extends HardRule {
  weight: number;
}

export interface EvaluationRuleDraftInput {
  name: string;
  description: string | null;
  hard_rules: HardRule[];
  weighted_rules: WeightedRule[];
  prompt_version: string;
}

export interface EvaluationRuleVersion {
  id: number;
  rule_set_id: number;
  version_number: number;
  status: RuleVersionStatus;
  hard_rules: HardRule[];
  weighted_rules: WeightedRule[];
  prompt_version: string;
  created_by: number;
  published_by: number | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationRuleSet {
  id: number;
  name: string;
  description: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
  versions: EvaluationRuleVersion[];
}

export async function listEvaluationRules(): Promise<EvaluationRuleSet[]> {
  return (await http.get<EvaluationRuleSet[]>("/evaluation-rules")).data;
}

export async function getEvaluationRule(id: number): Promise<EvaluationRuleSet> {
  return (await http.get<EvaluationRuleSet>(`/evaluation-rules/${id}`)).data;
}

export async function createRuleDraft(
  payload: EvaluationRuleDraftInput,
  ruleSetId?: number,
): Promise<EvaluationRuleSet | EvaluationRuleVersion> {
  if (ruleSetId === undefined) {
    return (await http.post<EvaluationRuleSet>("/evaluation-rules", payload)).data;
  }
  return (
    await http.post<EvaluationRuleVersion>(
      `/evaluation-rules/${ruleSetId}/versions`,
      payload,
    )
  ).data;
}

export async function updateRuleDraft(
  versionId: number,
  payload: EvaluationRuleDraftInput,
): Promise<EvaluationRuleVersion> {
  return (
    await http.put<EvaluationRuleVersion>(
      `/evaluation-rule-versions/${versionId}`,
      payload,
    )
  ).data;
}

export async function publishRuleVersion(
  versionId: number,
): Promise<EvaluationRuleVersion> {
  return (
    await http.post<EvaluationRuleVersion>(
      `/evaluation-rule-versions/${versionId}/publish`,
    )
  ).data;
}

export async function retireRuleVersion(
  versionId: number,
): Promise<EvaluationRuleVersion> {
  return (
    await http.post<EvaluationRuleVersion>(
      `/evaluation-rule-versions/${versionId}/retire`,
    )
  ).data;
}
