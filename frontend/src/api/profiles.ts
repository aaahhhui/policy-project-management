import http from "./http";

export interface ProfileResponse {
  code: string;
  display_name: string;
  data: Record<string, unknown>;
  verification_status: string;
}

export interface BusinessEntityResponse {
  seed_code: string;
  legal_name: string;
  data: Record<string, unknown>;
  verification_status: string;
}

export async function getSharedProfile(): Promise<ProfileResponse> {
  const response = await http.get<ProfileResponse>("/profiles/shared");
  return response.data;
}

export async function getBusinessEntities(): Promise<BusinessEntityResponse[]> {
  const response = await http.get<BusinessEntityResponse[]>("/profiles/entities");
  return response.data;
}
