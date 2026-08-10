import type { ProjectStatus } from "../../api/projects";

export interface ProjectLedgerFilters {
  q: string;
  primary_entity_seed_code: string;
  liaison_id: string;
  status: ProjectStatus | "";
  deadline_from: string;
  deadline_to: string;
  mine: boolean;
  page: number;
  page_size: 10 | 20 | 50;
}

const validStatuses: ProjectStatus[] = ["pending_application", "submitted", "succeeded", "rejected", "terminated"];
const pageSizes = [10, 20, 50] as const;

function positiveInteger(value: unknown, fallback: number): number {
  const parsed = typeof value === "string" || typeof value === "number" ? Number(value) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function one(value: unknown): string | undefined {
  return Array.isArray(value) ? value[0] : typeof value === "string" ? value : undefined;
}

export function filtersFromQuery(query: Record<string, unknown>): ProjectLedgerFilters {
  const pageSize = positiveInteger(one(query.page_size), 20);
  const status = one(query.status);
  return {
    q: one(query.q) ?? "",
    primary_entity_seed_code: one(query.primary_entity_seed_code) ?? "",
    liaison_id: one(query.liaison_id) ?? "",
    status: validStatuses.includes(status as ProjectStatus) ? status as ProjectStatus : "",
    deadline_from: one(query.deadline_from) ?? "",
    deadline_to: one(query.deadline_to) ?? "",
    mine: one(query.mine) === "1",
    page: positiveInteger(one(query.page), 1),
    page_size: pageSizes.includes(pageSize as 10 | 20 | 50) ? pageSize as 10 | 20 | 50 : 20,
  };
}

export function filtersToQuery(filters: ProjectLedgerFilters): Record<string, string> {
  const query: Record<string, string> = {};
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.primary_entity_seed_code.trim()) query.primary_entity_seed_code = filters.primary_entity_seed_code.trim();
  if (filters.liaison_id) query.liaison_id = filters.liaison_id;
  if (filters.status) query.status = filters.status;
  if (filters.deadline_from) query.deadline_from = filters.deadline_from;
  if (filters.deadline_to) query.deadline_to = filters.deadline_to;
  if (filters.mine) query.mine = "1";
  if (filters.page > 1) query.page = String(filters.page);
  if (filters.page_size !== 20) query.page_size = String(filters.page_size);
  return query;
}
