import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Search,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  FolderGit2,
} from "lucide-react";
import { useProject, useRuns } from "../lib/api";
import { Empty, ErrorState, Loading, Reveal, RunTable } from "../components/ui";
export function Runs({ onNew }: { onNew: () => void }) {
  const [offset, setOffset] = useState(0),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState("all");
  const query = useRuns(offset, 20);
  const filtered =
    query.data?.runs.filter(
      (r) =>
        (status === "all" || r.status === status) &&
        `${r.id} ${r.branch} ${r.status}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) || [];
  return (
    <>
      <Reveal className="page-heading">
        <div>
          <div className="eyebrow">THE WORK, IN PROGRESS</div>
          <h1>Test runs.</h1>
          <p>Every exploration, every result, all in one place.</p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={17} />
          New test run
        </button>
      </Reveal>
      <section className="panel">
        <div className="toolbar">
          <div className="input-icon search">
            <Search size={17} />
            <input
              aria-label="Search current page of runs"
              placeholder="Filter this page by ID, branch, or status…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Filter status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            {[
              "QUEUED",
              "CLONING",
              "ANALYZING",
              "BUILDING",
              "STARTING",
              "READY",
              "DISCOVERING",
              "TESTING",
              "ANALYZING_FAILURES",
              "COMPLETED",
              "DISCOVERY_COMPLETE",
              "FAILED",
              "CANCELLED",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => query.refetch()} />
        ) : filtered.length ? (
          <RunTable runs={filtered} />
        ) : (
          <Empty
            title="No runs here just yet."
            text={
              search || status !== "all"
                ? "Try a different filter. Filters apply to the current page."
                : "Your repository’s next chapter starts with a test."
            }
            action={search || status !== "all" ? undefined : onNew}
          />
        )}
        <div className="pagination">
          <span>
            {query.data?.total || 0} total runs · Page{" "}
            {Math.floor(offset / 20) + 1}
          </span>
          <div>
            <button
              aria-label="Previous page"
              className="icon-button"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              <ArrowLeft size={17} />
            </button>
            <button
              aria-label="Next page"
              className="icon-button"
              disabled={offset + 20 >= (query.data?.total || 0)}
              onClick={() => setOffset(offset + 20)}
            >
              <ArrowRight size={17} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
function ProjectCard({ id, lastRun }: { id: string; lastRun: string }) {
  const query = useProject(id);
  return (
    <Reveal className="project-card">
      <div className="project-card-top">
        <span className="repo-icon">
          <FolderGit2 size={24} />
        </span>
        <span className="eyebrow">REPOSITORY</span>
      </div>
      <h2>{query.data?.repository_url.split("/").pop() || id.slice(0, 8)}</h2>
      <p>
        {query.data?.repository_url.replace("https://github.com/", "") ||
          "Loading repository…"}
      </p>
      <div className="tags">
        <span>{query.data?.detected_framework || "Not detected yet"}</span>
        <span>{query.data?.default_branch || "Default branch"}</span>
      </div>
      {query.error && (
        <p className="form-error">Project details unavailable.</p>
      )}
      <Link className="text-link" to={`/runs/${lastRun}`}>
        Open latest run
        <ArrowUpRight size={17} />
      </Link>
    </Reveal>
  );
}
export function Projects({ onNew }: { onNew: () => void }) {
  const query = useRuns(0, 100);
  const projects = [
    ...new Map((query.data?.runs || []).map((r) => [r.project_id, r])).keys(),
  ];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ROOM FOR YOUR NEXT IDEA</span>
          <h1>Your projects.</h1>
          <p>Repositories represented in your latest 100 runs.</p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={17} />
          Test a repository
        </button>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : projects.length ? (
        <div className="project-grid">
          {projects.map((id) => (
            <ProjectCard
              id={id}
              key={id}
              lastRun={query.data!.runs.find((r) => r.project_id === id)!.id}
            />
          ))}
        </div>
      ) : (
        <div className="panel">
          <Empty
            title="Good projects deserve a second look."
            text="Start a run to bring your first repository into this workspace."
            action={onNew}
          />
        </div>
      )}
    </>
  );
}
