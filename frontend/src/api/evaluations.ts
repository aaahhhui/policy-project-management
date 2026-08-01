import http from "./http";

export interface EntityEvaluation {
  entity_seed_code: string;
  match_level: "high" | "medium" | "low" | "uncertain";
  score?: number;
  hard_rule_results?: Array<Record<string, unknown>>;
  weighted_rule_results?: Array<Record<string, unknown>>;
  evidence: string[];
  unmet_conditions: string[];
  risks: string[];
  recommended_action: string;
}

export interface EvaluationBatch {
  id: number;
  policy_version_id: number;
  status: "pending" | "running" | "succeeded" | "awaiting_confirmation" | "confirmed" | "cancelled" | "failed";
  prompt_version: string;
  adapter_key: string;
  model_name: string | null;
  rule_version_id?: number | null;
  rule_snapshot?: Record<string, unknown> | null;
  retry_count?: number;
  provider_request_id?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cancelled_by?: number | null;
  cancelled_at?: string | null;
  cancel_reason?: string | null;
  profile_snapshot: Array<Record<string, unknown>>;
  summary: string | null;
  key_conditions: string[] | null;
  conclusion: "recommend_apply" | "watch" | "not_recommended" | "uncertain" | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  entities: EntityEvaluation[];
}

export async function getEvaluations(policyId: number): Promise<EvaluationBatch[]> {
  return (await http.get<EvaluationBatch[]>(`/policies/${policyId}/evaluations`)).data;
}

export async function createEvaluation(policyId: number): Promise<EvaluationBatch> {
  return (await http.post<EvaluationBatch>(`/policies/${policyId}/evaluations`)).data;
}

export async function cancelEvaluation(batchId: number, reason: string | null): Promise<EvaluationBatch> {
  return (await http.post<EvaluationBatch>(`/evaluations/${batchId}/cancellation`, { reason })).data;
}

export interface EvaluationConfirmationInput {
  conclusion: NonNullable<EvaluationBatch["conclusion"]>;
  summary: string;
  key_conditions: string[];
  entities: EntityEvaluation[];
  change_reason: string | null;
}

export interface PrimaryEntityDecision {
  entity_seed_code: string;
  entity_legal_name: string;
  reason?: string | null;
  is_current?: boolean;
}

export async function confirmEvaluation(batchId: number, payload: EvaluationConfirmationInput) {
  return (await http.post(`/evaluations/${batchId}/confirmation`, payload)).data;
}

export async function selectPrimaryEntity(
  policyId: number,
  payload: { entity_seed_code: string; reason: string | null },
) {
  return (await http.put(`/policies/${policyId}/primary-entity`, payload)).data;
}

export async function getPrimaryEntityHistory(policyId: number): Promise<PrimaryEntityDecision[]> {
  return (await http.get<PrimaryEntityDecision[]>(`/policies/${policyId}/primary-entity-history`)).data;
}
