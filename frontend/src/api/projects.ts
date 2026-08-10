import http from "./http";

export type ProjectStatus =
  | "pending_application"
  | "submitted"
  | "succeeded"
  | "rejected"
  | "terminated";

export interface ProjectCapabilities {
  can_edit_project: boolean;
  can_update_progress: boolean;
  can_transition: boolean;
  can_correct_status: boolean;
  can_correct_primary_entity: boolean;
}

export type ProjectConversionWarning = "deadline_expired" | "deadline_unknown";

export interface ProjectPerson { id: number; display_name: string; }
export interface ProjectMemberDetail { id: number; user_id: number; display_name: string; added_at: string; }
export interface ProjectUserOption { id: number; display_name: string; role: string | null; }
export interface ProjectPolicySnapshot {
  id: number; title: string; conclusion: string; conclusion_source: string; conclusion_confirmed_at: string | null;
}
export interface ProjectEntitySnapshot { decision_id: number; seed_code: string; legal_name: string; }
export interface ProjectDates { deadline_on: string | null; submitted_on: string | null; result_on: string | null; }
export interface ProjectNotes { progress_note: string | null; result_note: string | null; termination_note: string | null; }
export interface ProjectStatusHistoryDetail {
  id: number; action: string; previous_status: ProjectStatus | null; new_status: ProjectStatus;
  actor: ProjectPerson; reason: string | null; related_date: string | null;
  before_values: Record<string, unknown>; after_values: Record<string, unknown>;
  from_version: number; to_version: number; occurred_at: string;
}
export interface ProjectAuditSummary {
  id: number; action: string; actor: ProjectPerson | null; reason: string | null;
  before_values: Record<string, unknown>; after_values: Record<string, unknown>; occurred_at: string;
}

export interface ProjectListItem {
  id: number; policy_id: number; name: string; policy_title: string;
  primary_entity_seed_code: string; primary_entity_legal_name: string;
  applicant_owner: ProjectPerson; liaison: ProjectPerson; status: ProjectStatus;
  deadline_on: string | null; updated_at: string; version: number; capabilities: ProjectCapabilities;
}
export interface ProjectPage { items: ProjectListItem[]; page: number; page_size: number; total: number; }
export interface ProjectSummary { total: number; by_status: Record<string, number>; convertible_policy_count: number; }
export interface ConvertiblePolicyItem {
  id: number; title: string; primary_entity_decision_id: number; primary_entity_seed_code: string;
  primary_entity_legal_name: string; deadline_on: string | null; conversion_warnings: ProjectConversionWarning[];
}
export interface ConvertiblePolicyPage { items: ConvertiblePolicyItem[]; page: number; page_size: number; total: number; }
export interface ProjectDetail {
  id: number; policy_id: number; name: string; primary_entity_decision_id: number;
  primary_entity_seed_code: string; primary_entity_legal_name: string; applicant_owner_id: number;
  applicant_owner_display_name: string; liaison_user_id: number; liaison_display_name: string;
  status: ProjectStatus; deadline_on: string | null; submitted_on: string | null; result_on: string | null;
  progress_note: string | null; result_note: string | null; termination_note: string | null; version: number;
  members: ProjectMemberDetail[]; conversion_warnings: ProjectConversionWarning[]; policy: ProjectPolicySnapshot;
  entity: ProjectEntitySnapshot; applicant_owner: ProjectPerson; liaison: ProjectPerson; dates: ProjectDates;
  notes: ProjectNotes; status_history: ProjectStatusHistoryDetail[]; recent_audits: ProjectAuditSummary[];
  capabilities: ProjectCapabilities;
}

export interface ProjectFilters {
  q?: string; primary_entity_seed_code?: string; liaison_user_id?: number; status?: ProjectStatus;
  deadline_from?: string; deadline_to?: string; mine?: boolean; page?: number; page_size?: 10 | 20 | 50;
}
export interface ProjectCreateInput {
  name?: string | null; liaison_user_id: number; member_user_ids?: number[]; deadline_on?: string | null;
}
export interface ProjectUpdateInput {
  expected_version: number; name?: string | null; deadline_on?: string | null; liaison_user_id?: number | null;
  member_user_ids?: number[] | null; submitted_on?: string | null; result_on?: string | null;
  progress_note?: string | null; result_note?: string | null; termination_note?: string | null;
}
export interface ProjectTransitionInput {
  expected_version: number; target_status: ProjectStatus; submitted_on?: string | null; result_on?: string | null;
  result_note?: string | null; termination_note?: string | null;
}
export interface ProjectCorrectionInput extends ProjectTransitionInput { reason?: string | null; }
export interface ProjectPrimaryEntityCorrectionInput {
  expected_version: number; primary_entity_decision_id: number; reason?: string | null;
}

export async function getProjectSummary(): Promise<ProjectSummary> {
  return (await http.get<ProjectSummary>("/projects/summary")).data;
}
export async function getProjects(filters: ProjectFilters = {}): Promise<ProjectPage> {
  return (await http.get<ProjectPage>("/projects", { params: filters })).data;
}
export async function getProject(id: number): Promise<ProjectDetail> {
  return (await http.get<ProjectDetail>(`/projects/${id}`)).data;
}
export async function getConvertiblePolicies(page = 1, pageSize = 20): Promise<ConvertiblePolicyPage> {
  return (await http.get<ConvertiblePolicyPage>("/policies/convertible", { params: { page, page_size: pageSize } })).data;
}
export async function getProjectUserOptions(): Promise<ProjectUserOption[]> {
  return (await http.get<ProjectUserOption[]>("/users/project-options")).data;
}
export async function createProjectFromPolicy(
  policyId: number, payload: ProjectCreateInput, idempotencyKey: string,
): Promise<ProjectDetail> {
  return (await http.post<ProjectDetail>(`/policies/${policyId}/project`, payload, {
    headers: { "Idempotency-Key": idempotencyKey },
  })).data;
}
export async function updateProject(id: number, payload: ProjectUpdateInput): Promise<ProjectDetail> {
  return (await http.patch<ProjectDetail>(`/projects/${id}`, payload)).data;
}
export async function transitionProject(id: number, payload: ProjectTransitionInput): Promise<ProjectDetail> {
  return (await http.post<ProjectDetail>(`/projects/${id}/transitions`, payload)).data;
}
export async function correctProjectStatus(id: number, payload: ProjectCorrectionInput): Promise<ProjectDetail> {
  return (await http.post<ProjectDetail>(`/projects/${id}/corrections`, payload)).data;
}
export async function correctProjectPrimaryEntity(
  id: number, payload: ProjectPrimaryEntityCorrectionInput,
): Promise<ProjectDetail> {
  return (await http.post<ProjectDetail>(`/projects/${id}/primary-entity-corrections`, payload)).data;
}
