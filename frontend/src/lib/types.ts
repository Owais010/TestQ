export interface Run {
  id: string;
  project_id: string;
  branch: string;
  commit_sha: string | null;
  status: string;
  failure_reason: string | null;
  failure_stage: string | null;
  cancellation_requested: boolean;
  discovery_enabled: boolean;
  testing_enabled: boolean;
  progress: Record<string, string> | null;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  ai_status?: string | null;
  ai_model?: string | null;
  ai_test_count?: number;
  ai_warning?: string | null;
  static_findings?: Record<string, unknown> | null;
  observations?: Record<string, unknown>[] | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export interface Project {
  id: string;
  repository_url: string;
  default_branch: string;
  detected_framework: string | null;
  detected_language: string | null;
}
export interface RunList {
  runs: Run[];
  total: number;
}
export interface Evidence {
  id: string;
  kind: string;
  page_url: string | null;
  url: string;
  size_bytes: number;
  media_type: string;
  sha256: string;
}
export interface PageRecord {
  url: string;
  title: string;
  status: number | null;
  navigation: string;
  links: unknown[];
  buttons: unknown[];
  inputs: unknown[];
  forms: unknown[];
}
export interface Discovery {
  status: string;
  pages: PageRecord[];
  api_endpoints: { method: string; path: string; statuses: number[] }[];
  observations: {
    kind: string;
    message: string;
    page_url: string;
    timestamp: string;
  }[];
}
export interface Log {
  id: string;
  source: string;
  level: string;
  message: string;
  timestamp: string;
}
export interface TestCase {
  id: string;
  title: string;
  type: string;
  priority: string;
  source: string;
  definition: unknown;
}
export interface TestResult {
  id: string;
  test_case_id: string;
  status: string;
  duration_ms: number;
  error: string | null;
  steps: unknown[];
  assertions: unknown[];
  http_status?: number | null;
  reproduction_count?: number;
  reproduction_total?: number;
  confirmed?: boolean;
}
export interface Failure {
  id: string;
  test_result_id?: string;
  test_case_id?: string;
  test_title?: string;
  test_type?: string;
  test_source?: string;
  title: string;
  severity: string;
  category?: string;
  summary: string;
  likely_root_cause: string;
  confidence: number;
  reproduction_steps: string[];
  evidence_references?: string[];
  classification?: string;
  reproduction_count?: number;
  reproduction_total?: number;
  confirmed?: boolean;
  http_status?: number | null;
}
export interface UniqueDefect {
  defect_id: string;
  signature: string;
  title: string;
  classification: string;
  severity: string;
  category: string;
  target: string;
  failed_assertion: string;
  test_count: number;
  seen_in_tests: string[];
  display_badge: string;
  summary: string;
  likely_root_cause: string;
  reproduction_steps: string[];
  evidence_references: string[];
  primary_failure_id?: string;
  reproduction_count: number;
  reproduction_total: number;
}
export const terminal = (r: Run) =>
  Boolean(r.finished_at) ||
  ["COMPLETED", "FAILED", "CANCELLED", "DISCOVERY_COMPLETE"].includes(r.status);
export const statusLabel = (s: string) => s.toLowerCase().replaceAll("_", " ");
export function date(value: string) {
  return new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z",
  ).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function duration(run: Run) {
  if (!run.started_at) return "—";
  const parse = (s: string) =>
    Date.parse(s.endsWith("Z") || /[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
  const seconds = Math.max(
    0,
    Math.round(
      ((run.finished_at ? parse(run.finished_at) : Date.now()) -
        parse(run.started_at)) /
        1000,
    ),
  );
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
