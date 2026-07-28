import http from "./http";

export interface EntityEvaluation {
  entity_seed_code: string;
  match_level: "high" | "medium" | "low" | "uncertain";
  evidence: string[];
  unmet_conditions: string[];
  risks: string[];
  recommended_action: string;
}

export interface EvaluationBatch {
  id: number;
  policy_version_id: number;
  status: "pending" | "running" | "succeeded" | "failed";
  prompt_version: string;
  adapter_key: string;
  model_name: string | null;
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
