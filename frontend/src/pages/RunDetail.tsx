import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Download,
  FileImage,
  FileText,
  GitBranch,
  OctagonX,
  RefreshCw,
  ScanLine,
} from "lucide-react";
import { api, ApiError, base, evidenceUrl, useRun } from "../lib/api";
import TestPlan from "../components/TestPlan";
import {
  date,
  duration,
  terminal,
  type Discovery,
  type Evidence,
  type Failure,
  type Log,
  type TestCase,
  type TestResult,
} from "../lib/types";
import {
  Empty,
  ErrorState,
  Loading,
  ProjectName,
  Status,
} from "../components/ui";
const tabs = [
  "Overview",
  "Application map",
  "Strategy",
  "Test plan",
  "Test results",
  "Evidence",
  "Logs",
  "Analysis",
] as const;
export default function RunDetail() {
  const { id = "" } = useParams();
  const [tab, setTab] = useState<(typeof tabs)[number]>("Overview");
  const query = useRun(id);
  const client = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api(`/api/test-runs/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["run", id] });
      client.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  if (query.isPending) return <Loading />;
  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const run = query.data!;
  const stages = Object.entries(run.progress || {}).filter(
    ([key]) => key !== "discovery_complete",
  );
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeft size={15} />
        All test runs
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <span className="eyebrow">RUN / {id.slice(0, 8)}</span>
          <h1 className="project-title">
            <ProjectName id={run.project_id} />
          </h1>
          <p>
            <GitBranch size={14} />
            {run.branch || "Default branch"} <span>·</span>
            {run.commit_sha?.slice(0, 7) || "Commit pending"} <span>·</span>
            {date(run.created_at)}
          </p>
        </div>
        <div className="heading-actions">
          {run.ai_model && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                padding: "0.3rem 0.6rem",
                borderRadius: "4px",
                fontSize: "0.75rem",
                fontWeight: 600,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid var(--border)",
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background:
                    run.ai_status === "READY"
                      ? "#10b981"
                      : run.ai_status === "DEGRADED"
                        ? "#f59e0b"
                        : "#ef4444",
                }}
              />
              AI: {run.ai_model} ({run.ai_status || "UNKNOWN"})
            </span>
          )}
          <a
            href={`${base}/api/test-runs/${id}/report/html`}
            target="_blank"
            rel="noopener noreferrer"
            className="button secondary"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.75rem", fontSize: "0.8rem" }}
          >
            <Download size={14} />
            QA Report
          </a>
          <Status value={run.status} />
          {!terminal(run) && (
            <button
              className="button secondary danger"
              disabled={cancel.isPending || run.cancellation_requested}
              onClick={() => {
                if (
                  window.confirm(
                    "Stop this run? The sandbox will be cleaned up and available evidence retained.",
                  )
                )
                  cancel.mutate();
              }}
            >
              <OctagonX size={16} />
              {run.cancellation_requested
                ? "Cancellation requested"
                : cancel.isPending
                  ? "Cancelling…"
                  : "Cancel run"}
            </button>
          )}
        </div>
      </div>
      {cancel.error && (
        <div className="form-error" role="alert">
          {cancel.error.message}
        </div>
      )}
      {run.ai_status === "DEGRADED" && (
        <div className="failure-banner" style={{ borderLeft: "4px solid #f59e0b", background: "rgba(245, 158, 11, 0.08)", padding: "1rem", borderRadius: "6px", marginBottom: "1rem" }}>
          <strong style={{ color: "#f59e0b" }}>AI ANALYSIS DEGRADED</strong>
          <p style={{ margin: "0.25rem 0 0" }}>
            {run.ai_warning || "Deterministic testing completed, but AI-generated adversarial tests were unavailable."}
          </p>
        </div>
      )}
      {run.ai_status === "UNAVAILABLE" && (
        <div className="failure-banner" style={{ borderLeft: "4px solid #ef4444", background: "rgba(239, 68, 68, 0.08)", padding: "1rem", borderRadius: "6px", marginBottom: "1rem" }}>
          <strong style={{ color: "#ef4444" }}>AI ENGINE UNAVAILABLE</strong>
          <p style={{ margin: "0.25rem 0 0" }}>
            {run.ai_warning || "Local Ollama model was unavailable. Deterministic tests executed."}
          </p>
        </div>
      )}
      {run.failure_reason && (
        <div className="failure-banner">
          <strong>{run.failure_stage || "Run"} needs attention</strong>
          <p>{run.failure_reason}</p>
        </div>
      )}
      <div className="detail-tabs" role="tablist" aria-label="Run details">
        {tabs.map((item) => (
          <button
            role="tab"
            aria-selected={tab === item}
            id={`tab-${item}`}
            aria-controls="detail-panel"
            tabIndex={0}
            key={item}
            className={tab === item ? "selected" : ""}
            onClick={() => setTab(item)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                event.preventDefault();
                const next =
                  tabs[
                    (tabs.indexOf(item) +
                      (event.key === "ArrowRight" ? 1 : tabs.length - 1)) %
                      tabs.length
                  ];
                setTab(next);
                document.getElementById(`tab-${next}`)?.focus();
              }
            }}
          >
            {item}
          </button>
        ))}
      </div>
      <div id="detail-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "Overview" ? (
          <>
            <div className="detail-stats">
              {[
                ["Duration", duration(run)],
                ["Tests", run.total_tests],
                ["Passed", run.passed_tests],
                ["Failed", run.failed_tests],
              ].map(([name, value]) => (
                <div key={name}>
                  <span>{name}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>The journey so far.</h2>
                  <p>
                    {terminal(run)
                      ? "Run finished. Explore the retained results and evidence."
                      : "Live updates every three seconds."}
                  </p>
                </div>
                <ScanLine size={22} />
              </div>
              <div className="pipeline">
                {stages.map(([stage, status], i) => (
                  <div className={`pipeline-step ${status}`} key={stage}>
                    <span className="step-marker">
                      {status === "completed" ? (
                        <Check size={15} />
                      ) : (
                        String(i + 1).padStart(2, "0")
                      )}
                    </span>
                    <div>
                      <strong>{stage.replaceAll("_", " ")}</strong>
                      <small>
                        {status === "pending" && terminal(run)
                          ? "Not executed"
                          : status.replaceAll("_", " ")}
                      </small>
                    </div>
                    {status === "in_progress" && (
                      <RefreshCw className="spin" size={16} />
                    )}
                  </div>
                ))}
              </div>
            </section>
            <div className="context-note">
              <strong>Evidence over assumptions.</strong>
              <p>
                Discovery records what the browser observed. Discovery
                completion is not a passing test verdict. Review individual test
                results and supporting evidence.
              </p>
            </div>
          </>
        ) : tab === "Strategy" || tab === "Test plan" ? (
          <TestPlan id={id} active={!terminal(run)} view={tab} />
        ) : (
          <RunSection id={id} tab={tab} active={!terminal(run)} />
        )}
      </div>
    </>
  );
}
function RunSection({
  id,
  tab,
  active,
}: {
  id: string;
  tab: (typeof tabs)[number];
  active: boolean;
}) {
  const endpoints: Record<string, string> = {
    "Application map": "discovery",
    "Test results": "test-results",
    Evidence: "evidence",
    Logs: "logs",
    Analysis: "failures",
  };
  const endpoint = endpoints[tab];
  const query = useQuery({
    queryKey: ["run-section", id, endpoint],
    queryFn: ({ signal }) =>
      api<
        | Discovery
        | { evidence: Evidence[] }
        | { logs: Log[] }
        | { test_results: TestResult[] }
        | { failures: Failure[] }
      >(`/api/test-runs/${id}/${endpoint}`, { signal }),
    refetchInterval: active ? 4000 : false,
  });
  const cases = useQuery({
    queryKey: ["test-cases", id],
    queryFn: ({ signal }) =>
      api<{ test_cases: TestCase[] }>(`/api/test-runs/${id}/test-cases`, {
        signal,
      }),
    enabled: tab === "Test results",
    refetchInterval: active ? 5000 : false,
  });
  if (query.isPending) return <Loading />;
  if (query.error) {
    if (query.error instanceof ApiError && query.error.status === 404)
      return (
        <div className="panel">
          <Empty
            title="Nothing to review here yet."
            text="This run hasn’t produced this information. It will appear when the relevant stage completes."
          />
        </div>
      );
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  }
  if (tab === "Application map") {
    const map = query.data as Discovery;
    return (
      <>
        <div className="section-heading">
          <h2>{map.pages.length} pages. One application.</h2>
          <span className="eyebrow">{map.status}</span>
        </div>
        <div className="map-grid">
          {map.pages.map((page) => (
            <article className="page-card" key={page.url}>
              <div>
                <ScanLine size={20} />
                <span
                  className={`status ${page.navigation === "ok" ? "good" : "bad"}`}
                >
                  {page.status || page.navigation}
                </span>
              </div>
              <h3>{page.title || "Untitled page"}</h3>
              <code>{page.url}</code>
              <div className="page-counts">
                <span>{page.links.length} links</span>
                <span>{page.buttons.length} buttons</span>
                <span>{page.inputs.length} inputs</span>
                <span>{page.forms.length} forms</span>
              </div>
            </article>
          ))}
        </div>
        {!map.pages.length && <Empty title="No pages captured yet." />}
        <section className="panel compact">
          <h2>Observed endpoints</h2>
          {map.api_endpoints.length ? (
            map.api_endpoints.map((api, i) => (
              <div className="endpoint" key={i}>
                <span className="tag">{api.method}</span>
                <code>{api.path}</code>
                <span>{api.statuses.join(", ")}</span>
              </div>
            ))
          ) : (
            <p className="muted">No API endpoints observed.</p>
          )}
        </section>
        <section className="panel compact">
          <h2>
            Browser observations{" "}
            <span className="count">{map.observations.length}</span>
          </h2>
          {map.observations.map((o, i) => (
            <details key={i}>
              <summary>
                {o.kind.replaceAll("_", " ")} <small>{o.page_url}</small>
              </summary>
              <pre>{o.message}</pre>
            </details>
          ))}
          {!map.observations.length && (
            <p className="muted">No observations recorded.</p>
          )}
        </section>
      </>
    );
  }
  if (tab === "Evidence") {
    const items = (query.data as { evidence: Evidence[] }).evidence;
    return items.length ? (
      <div className="evidence-grid">
        {items.map((item) => (
          <article className="evidence-card" key={item.id}>
            {item.media_type === "image/png" ? (
              <img
                loading="lazy"
                src={evidenceUrl(item.url)}
                alt={`Captured ${item.page_url || "application"} screenshot`}
              />
            ) : (
              <div className="file-preview">
                {item.kind.includes("trace") ? (
                  <ScanLine size={42} />
                ) : item.media_type.startsWith("image") ? (
                  <FileImage size={42} />
                ) : (
                  <FileText size={42} />
                )}
              </div>
            )}
            <div className="evidence-body">
              <h3>{item.kind.replaceAll("_", " ")}</h3>
              <p>{item.page_url || "Run artifact"}</p>
              <div>
                <small>
                  {(item.size_bytes / 1024).toFixed(1)} KB · Retained artifact
                </small>
                <a
                  className="icon-button"
                  href={evidenceUrl(item.url)}
                  download
                  aria-label={`Download ${item.kind}`}
                >
                  <Download size={17} />
                </a>
              </div>
            </div>
          </article>
        ))}
      </div>
    ) : (
      <Empty
        title="Evidence will find its place here."
        text="Artifacts are exported from the sandbox before cleanup."
      />
    );
  }
  if (tab === "Logs")
    return <LogViewer logs={(query.data as { logs: Log[] }).logs} />;
  if (tab === "Analysis") {
    const failures = (query.data as { failures: Failure[] }).failures;
    return failures.length ? (
      <div className="analysis-list">
        {failures.map((f) => (
          <article className="panel compact" key={f.id}>
            <div className="section-heading">
              <div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.4rem" }}>
                  <span
                    style={{
                      padding: "0.2rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      background: f.classification === "CONFIRMED BUG" ? "rgba(239, 68, 68, 0.15)" : "rgba(245, 158, 11, 0.15)",
                      color: f.classification === "CONFIRMED BUG" ? "#ef4444" : "#f59e0b",
                      border: `1px solid ${f.classification === "CONFIRMED BUG" ? "rgba(239, 68, 68, 0.4)" : "rgba(245, 158, 11, 0.4)"}`,
                    }}
                  >
                    {f.classification || "POSSIBLE BUG"}
                  </span>
                  {f.reproduction_count && (
                    <span
                      style={{
                        padding: "0.2rem 0.5rem",
                        borderRadius: "4px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: f.confirmed ? "rgba(16, 185, 129, 0.15)" : "rgba(107, 114, 128, 0.15)",
                        color: f.confirmed ? "#10b981" : "#9ca3af",
                        border: `1px solid ${f.confirmed ? "rgba(16, 185, 129, 0.4)" : "rgba(107, 114, 128, 0.4)"}`,
                      }}
                    >
                      CONFIRMED {f.reproduction_count} / {f.reproduction_total || 3} REPRODUCTIONS
                    </span>
                  )}
                </div>
                <h2>{f.title}</h2>
              </div>
              <span className="status bad">{f.severity}</span>
            </div>
            <p>{f.summary}</p>
            <h4>Likely root cause</h4>
            <p>{f.likely_root_cause}</p>
            <h4>Reproduction steps</h4>
            <ol>
              {f.reproduction_steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
            {f.evidence_references && f.evidence_references.length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <h4>Evidence Artifacts</h4>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
                  {f.evidence_references.map((refUrl, i) => (
                    <a
                      key={i}
                      href={refUrl.startsWith("http") ? refUrl : `${base}${refUrl}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="button secondary"
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <FileImage size={15} />
                      View Evidence Artifact
                      <ArrowUpRight size={14} />
                    </a>
                  ))}
                </div>
              </div>
            )}
            <small className="muted" style={{ display: "block", marginTop: "1rem" }}>
              AI assessment · {Math.round(f.confidence * 100)}% confidence ·
              Evidence-backed classification
            </small>
          </article>
        ))}
      </div>
    ) : (
      <Empty
        title="No analysis recorded."
        text="This does not imply a bug-free application. Analysis appears only when the backend has produced findings."
      />
    );
  }
  const results = (query.data as { test_results: TestResult[] }).test_results;
  return (
    <>
      {cases.error && (
        <p className="form-error">
          Test names couldn’t load; results remain available by ID.
        </p>
      )}
      {results.length ? (
        <div className="panel compact">
          <h2>Individual test results</h2>
          {results.map((result) => (
            <details key={result.id}>
              <summary>
                <Status value={result.status} />
                {(() => {
                  const tc = cases.data?.test_cases.find((c) => c.id === result.test_case_id);
                  const src = tc?.source;
                  return (
                    <>
                      {src === "demo_deterministic" && (
                        <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "0.15rem 0.45rem", borderRadius: "4px", background: "rgba(99, 102, 241, 0.2)", color: "#a5b4fc", border: "1px solid rgba(99, 102, 241, 0.4)", whiteSpace: "nowrap" }}>
                          DEMO DETERMINISTIC
                        </span>
                      )}
                      {src === "ai" && (
                        <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "0.15rem 0.45rem", borderRadius: "4px", background: "rgba(168, 85, 247, 0.2)", color: "#d8b4fe", border: "1px solid rgba(168, 85, 247, 0.4)", whiteSpace: "nowrap" }}>
                          AI GENERATED
                        </span>
                      )}
                      {src === "baseline" && (
                        <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "0.15rem 0.45rem", borderRadius: "4px", background: "rgba(107, 114, 128, 0.2)", color: "#9ca3af", border: "1px solid rgba(107, 114, 128, 0.4)", whiteSpace: "nowrap" }}>
                          BASELINE
                        </span>
                      )}
                      <strong>{tc?.title || result.test_case_id}</strong>
                    </>
                  );
                })()}
                {result.reproduction_count && (
                  <span style={{ fontSize: "0.72rem", color: result.confirmed ? "#10b981" : "#f59e0b", marginLeft: "auto", marginRight: "0.5rem" }}>
                    {result.reproduction_count}/{result.reproduction_total || 3} repro
                  </span>
                )}
                <small>{Math.round(result.duration_ms)} ms</small>
                <ArrowUpRight size={16} />
              </summary>
              {result.error && <p className="form-error">{result.error}</p>}
              <h4>Assertions & steps</h4>
              <pre>
                {JSON.stringify(
                  { assertions: result.assertions, steps: result.steps },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))}
        </div>
      ) : (
        <Empty
          title="Results need a little groundwork."
          text="Enable Discover & test when starting a run. Results appear as the executor records them."
        />
      )}
    </>
  );
}
function LogViewer({ logs }: { logs: Log[] }) {
  const [filter, setFilter] = useState("");
  const filtered = logs.filter((log) =>
    `${log.message} ${log.source} ${log.level}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  return (
    <section className="panel">
      <div className="toolbar">
        <h2>
          Execution journal <span className="count">{logs.length}</span>
        </h2>
        <input
          aria-label="Filter logs"
          placeholder="Search logs…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className="log-viewer">
        {filtered.slice(-500).map((log) => (
          <div className="log-line" key={log.id}>
            <time>{date(log.timestamp)}</time>
            <span className={log.level === "ERROR" ? "log-error" : ""}>
              {log.level}
            </span>
            <span>{log.source}</span>
            <pre>{log.message}</pre>
          </div>
        ))}
        {!filtered.length && <p>No matching log entries.</p>}
      </div>
      {filtered.length > 500 && (
        <p className="muted compact">
          Showing the latest 500 matching records.
        </p>
      )}
    </section>
  );
}
