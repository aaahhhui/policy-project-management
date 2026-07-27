import http from "./http";

export type CollectionStatus = "pending" | "running" | "succeeded" | "partial_failed" | "failed";

export interface CollectionTaskItem {
  id: number;
  status: CollectionStatus;
  error_message: string | null;
}

export interface CollectionTask {
  id: number;
  source_id: number;
  status: CollectionStatus;
  discovered_count: number;
  succeeded_count: number;
  failed_count: number;
  items: CollectionTaskItem[];
}

export async function collectSource(sourceId: number): Promise<CollectionTask> {
  return (await http.post<CollectionTask>(`/sources/${sourceId}/collect`)).data;
}

export async function getCollectionTask(taskId: number): Promise<CollectionTask> {
  return (await http.get<CollectionTask>(`/collection-tasks/${taskId}`)).data;
}
