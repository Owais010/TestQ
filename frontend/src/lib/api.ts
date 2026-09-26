import { useQuery } from "@tanstack/react-query";
import type { RunList, Project, Run } from "./types";
export const base = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(base + path, {
    ...init,
    signal: init?.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      /* HTTP errors may not contain JSON */
    }
    throw new ApiError(
      response.status,
      detail || `Request failed (${response.status})`,
    );
  }
  return response.json();
}
export const useRuns = (offset = 0, limit = 12) =>
  useQuery({
    queryKey: ["runs", offset, limit],
    queryFn: ({ signal }) =>
      api<RunList>(`/api/test-runs?limit=${limit}&offset=${offset}`, {
        signal,
      }),
    refetchInterval: 5000,
  });
export const useProject = (id: string) =>
  useQuery({
    queryKey: ["project", id],
    queryFn: ({ signal }) => api<Project>(`/api/projects/${id}`, { signal }),
    enabled: Boolean(id),
    staleTime: 60000,
  });
export const useRun = (id: string) =>
  useQuery({
    queryKey: ["run", id],
    queryFn: ({ signal }) => api<Run>(`/api/test-runs/${id}`, { signal }),
    enabled: Boolean(id),
    refetchInterval: 3000,
  });
export function evidenceUrl(path: string) {
  return /^\/api\/test-runs\/[^/]+\/evidence\/[^/]+$/.test(path)
    ? base + path
    : "#";
}
