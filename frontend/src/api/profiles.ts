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

export interface VersionedProfileResponse {
  code: string;
  display_name: string;
  data: Record<string, unknown>;
  verification_status: string;
  version: number;
  recent_audits: ProfileAuditSummary[];
}

export interface VersionedBusinessEntityResponse {
  seed_code: string;
  legal_name: string;
  data: Record<string, unknown>;
  verification_status: string;
  version: number;
  recent_audits: ProfileAuditSummary[];
}

export type ProfileResponse = VersionedProfileResponse;
export type BusinessEntityResponse = VersionedBusinessEntityResponse;

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

export async function getSharedProfile(): Promise<VersionedProfileResponse> {
  return (await http.get<VersionedProfileResponse>("/profiles/shared")).data;
}

export async function getBusinessEntities(): Promise<VersionedBusinessEntityResponse[]> {
  return (await http.get<VersionedBusinessEntityResponse[]>("/profiles/entities")).data;
}

export async function updateSharedProfile(
  payload: ProfilePatchInput,
): Promise<VersionedProfileResponse> {
  return (await http.patch<VersionedProfileResponse>("/profiles/shared", payload)).data;
}

export async function updateBusinessEntity(
  seedCode: string,
  payload: BusinessEntityPatchInput,
): Promise<VersionedBusinessEntityResponse> {
  return (
    await http.patch<VersionedBusinessEntityResponse>(
      `/profiles/entities/${seedCode}`,
      payload,
    )
  ).data;
}
