import http from "./http";

export type PolicyConclusion = "recommend_apply" | "watch" | "not_recommended" | "uncertain";
export type PolicyCurrentConclusion = PolicyConclusion | "pending_confirmation";

export interface PolicyListItem {
  id: number; title: string; document_number: string | null;
  published_on: string | null; deadline_on: string | null;
  current_conclusion: PolicyCurrentConclusion; conclusion_confirmed: boolean; sources: string[];
  converted_to_project: boolean; project_id: number | null; project_name: string | null;
}
export interface PolicyPage { items: PolicyListItem[]; page: number; page_size: number; total: number; }
export interface SourceOption { id: number; name: string; }
export interface PolicyVersion {
  id: number; version_number: number; title: string; body_text: string; body_html: string;
  collected_at: string; snapshot_url: string;
}
export interface PolicyDiscovery {
  id: number; source_id: number; source_name: string; channel_id: number; channel_name: string;
  original_url: string; first_seen_at: string; last_seen_at: string;
}
export interface PolicyAttachment {
  id: number; display_name: string; source_url: string; status: string;
  content_type: string | null; error_message: string | null; download_url: string | null;
}
export interface PolicyDetail {
  id: number; title: string; document_number: string | null;
  published_on: string | null; deadline_on: string | null;
  current_conclusion: PolicyCurrentConclusion; conclusion_confirmed: boolean;
  current_conclusion_source: "system_suggestion" | "evaluation_confirmation" | "manual_override";
  conclusion_confirmed_at: string | null;
  converted_to_project: boolean; project_id: number | null; project_name: string | null;
  current_evaluation_batch_id: number | null; current_version: PolicyVersion;
  discoveries: PolicyDiscovery[]; attachments: PolicyAttachment[];
}
export interface PolicyConclusionDecision {
  id: number; policy_id: number; evaluation_batch_id: number;
  previous_conclusion: PolicyConclusion; conclusion: PolicyConclusion;
  source: "evaluation_confirmation" | "manual_override"; reason: string | null;
  decided_by: number; decided_at: string;
}
export interface PolicyFilters {
  q?: string; source_id?: number; published_from?: string; published_to?: string;
  page?: number; page_size?: number;
}

export async function getPolicies(params: PolicyFilters = {}): Promise<PolicyPage> {
  return (await http.get<PolicyPage>("/policies", { params })).data;
}
export async function getPolicySourceOptions(): Promise<SourceOption[]> {
  return (await http.get<SourceOption[]>("/policies/source-options")).data;
}
export async function getPolicy(id: number): Promise<PolicyDetail> {
  return (await http.get<PolicyDetail>(`/policies/${id}`)).data;
}
export async function getPolicyVersions(id: number): Promise<PolicyVersion[]> {
  return (await http.get<PolicyVersion[]>(`/policies/${id}/versions`)).data;
}
export async function getPolicyConclusionHistory(id: number): Promise<PolicyConclusionDecision[]> {
  return (await http.get<PolicyConclusionDecision[]>(`/policies/${id}/conclusion-decisions`)).data;
}
export async function adjustPolicyConclusion(
  id: number,
  payload: { conclusion: PolicyConclusion; reason: string },
): Promise<PolicyConclusionDecision> {
  return (await http.post<PolicyConclusionDecision>(`/policies/${id}/conclusion-decisions`, payload)).data;
}
