import http from "./http";

export type ProfileAuditAction = "enterprise_profile_updated" | "business_entity_updated";
export type ProfileAuditObjectType = "enterprise_profile" | "business_entity";

export interface ProfileAuditSummary {
  id: number;
  action: ProfileAuditAction;
  actor_id: number;
  actor_display_name: string;
  object_type: ProfileAuditObjectType;
  object_id: number;
  changed_fields: string[];
  before_values: Record<string, unknown>;
  after_values: Record<string, unknown>;
  occurred_at: string;
}

export interface ProfileResponse {
  code: string;
  display_name: string;
  data: Record<string, unknown>;
  verification_status: string;
  version: number;
  recent_audits: ProfileAuditSummary[];
}

export interface BusinessEntityResponse {
  seed_code: string;
  legal_name: string;
  data: Record<string, unknown>;
  verification_status: string;
  version: number;
  recent_audits: ProfileAuditSummary[];
}

export interface ProfilePatchInput {
  expected_version: number;
  display_name?: string;
  data?: Record<string, unknown>;
  verification_status?: string;
}

export interface BusinessEntityPatchInput {
  expected_version: number;
  legal_name?: string;
  data?: Record<string, unknown>;
  verification_status?: string;
}

export async function getSharedProfile(): Promise<ProfileResponse> {
  return (await http.get<ProfileResponse>("/profiles/shared")).data;
}

export async function getBusinessEntities(): Promise<BusinessEntityResponse[]> {
  return (await http.get<BusinessEntityResponse[]>("/profiles/entities")).data;
}

export async function updateSharedProfile(payload: ProfilePatchInput): Promise<ProfileResponse> {
  return (await http.patch<ProfileResponse>("/profiles/shared", payload)).data;
}

export async function updateBusinessEntity(
  seedCode: string,
  payload: BusinessEntityPatchInput,
): Promise<BusinessEntityResponse> {
  return (await http.patch<BusinessEntityResponse>(`/profiles/entities/${seedCode}`, payload)).data;
}
