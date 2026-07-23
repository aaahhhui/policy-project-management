import http from "./http";

export type AdapterStatus = "ready" | "pending";

export interface SourceChannel {
  id?: number;
  code: string;
  name: string;
  list_url: string;
  is_enabled: boolean;
}

export interface PolicySource {
  id: number;
  name: string;
  home_url: string;
  adapter_status: AdapterStatus;
  is_enabled: boolean;
  created_by: number;
  updated_by: number;
  channels: SourceChannel[];
  latest_collection_at: string | null;
  latest_result: string | null;
}

export interface SourceCreateInput {
  name: string;
  home_url: string;
  channels: Omit<SourceChannel, "id">[];
}

export interface SourceUpdateInput extends SourceCreateInput {
  is_enabled?: boolean;
}

export async function getSources(): Promise<PolicySource[]> {
  return (await http.get<PolicySource[]>("/sources")).data;
}

export async function createSource(payload: SourceCreateInput): Promise<PolicySource> {
  return (await http.post<PolicySource>("/sources", payload)).data;
}

export async function updateSource(id: number, payload: Partial<SourceUpdateInput>): Promise<PolicySource> {
  return (await http.patch<PolicySource>(`/sources/${id}`, payload)).data;
}

export async function toggleSource(id: number): Promise<PolicySource> {
  return (await http.post<PolicySource>(`/sources/${id}/toggle`)).data;
}
