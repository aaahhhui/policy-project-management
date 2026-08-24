import http from "./http";

export type RecognitionStatus =
  | "recognizing"
  | "ready_to_enable"
  | "enabled"
  | "pending_verification"
  | "rejected"
  | "disabled";

export type RecognitionKind =
  | "rss_atom"
  | "supported_government_site"
  | "public_listing_page"
  | "one_off_policy_link";

export interface PolicySource {
  id: number;
  name: string;
  entry_url: string;
  region_labels: string[];
  topic_labels: string[];
  recognition_status: RecognitionStatus;
  recognition_kind: RecognitionKind | null;
  recognition_summary: string;
  previewed_at: string | null;
  owner_confirmed_at: string | null;
  enabled_at: string | null;
  disabled_at: string | null;
  version: number;
  latest_collection_at: string | null;
  latest_result: string | null;
}

export interface SourcePage {
  items: PolicySource[];
  page: number;
  page_size: number;
  total: number;
}

export interface SourceCreateInput {
  name: string;
  entry_url: string;
  region_labels: string[];
  topic_labels: string[];
}

export async function getSources(page: number, pageSize: number): Promise<SourcePage> {
  return (await http.get<SourcePage>("/sources", { params: { page, page_size: pageSize } })).data;
}

export async function createSource(payload: SourceCreateInput): Promise<PolicySource> {
  return (await http.post<PolicySource>("/sources", payload)).data;
}

export async function retrySourceRecognition(id: number, representativeUrl?: string): Promise<PolicySource> {
  const payload = representativeUrl ? { representative_url: representativeUrl } : {};
  return (await http.post<PolicySource>(`/sources/${id}/recognition-retries`, payload)).data;
}

export async function enableSource(id: number, expectedVersion: number): Promise<PolicySource> {
  return (await http.post<PolicySource>(`/sources/${id}/enable`, { expected_version: expectedVersion })).data;
}

export async function disableSource(id: number, expectedVersion: number): Promise<PolicySource> {
  return (await http.post<PolicySource>(`/sources/${id}/disable`, { expected_version: expectedVersion })).data;
}
