import http from "./http";
export type NotificationStatus = "pending" | "sending" | "retry_wait" | "succeeded" | "failed";

export interface NotificationListItem {
  id: number; event_type: string; display_type: string; object_type: string; object_id: number;
  object_name: string; detail_path: string; triggered_at: string; status: NotificationStatus;
  attempt_count: number; send_round: number; round_attempt_count: number;
  next_attempt_at: string | null; sent_at: string | null; last_error_code: string | null;
  last_failure_summary: string | null; version: number;
}
export interface NotificationAttempt {
  id: number; attempt_number: number; trigger_type: string; started_at: string;
  finished_at: string | null; result: string | null; http_status: number | null;
  provider_error_code: string | null; failure_summary: string | null;
}
export interface NotificationDetail extends NotificationListItem {
  message_snapshot: Record<string, unknown>; attempts: NotificationAttempt[];
}
export interface NotificationPage { items: NotificationListItem[]; page: number; page_size: number; total: number; }
export interface NotificationFilters {
  event_type?: string; status?: NotificationStatus; triggered_from?: string; triggered_to?: string;
  page?: number; page_size?: 10 | 20 | 50;
}

export async function listNotifications(filters: NotificationFilters = {}): Promise<NotificationPage> {
  return (await http.get<NotificationPage>("/notifications", { params: filters })).data;
}
export async function getNotification(id: number): Promise<NotificationDetail> {
  return (await http.get<NotificationDetail>(`/notifications/${id}`)).data;
}
export async function retryNotification(id: number, expectedVersion: number): Promise<NotificationDetail> {
  return (await http.post<NotificationDetail>(`/notifications/${id}/retry`, { expected_version: expectedVersion })).data;
}
