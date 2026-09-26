import { motion } from "motion/react";
import { useMotionPreference } from "../lib/motion";
import type { ReactNode } from "react";
import {
  ArrowUpRight,
  FolderGit2,
  Plus,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useProject } from "../lib/api";
import { date, duration, statusLabel, type Run } from "../lib/types";
export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduced = useMotionPreference();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-20px" }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
export function Status({ value }: { value: string }) {
  const tone = ["COMPLETED", "DISCOVERY_COMPLETE", "PASS", "READY"].includes(
    value,
  )
    ? "good"
    : ["FAILED", "FAIL", "ERROR", "TIMEOUT"].includes(value)
      ? "bad"
      : value === "CANCELLED"
        ? "muted"
        : "active";
  return (
    <span className={`status ${tone}`}>
      <i />
      {statusLabel(value)}
    </span>
  );
}
export function Empty({
  title = "A fresh start.",
  text = "Your next project begins here.",
  action,
}: {
  title?: string;
  text?: string;
  action?: () => void;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FolderGit2 size={26} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <button className="button secondary" onClick={action}>
          <Plus size={16} />
          Start a run
        </button>
      )}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <TriangleAlert size={21} />
      <div>
        <strong>We couldn’t load this view.</strong>
        <p>
          {error.message.includes("fetch")
            ? "Check that the TestQ backend is running on port 8000, then try again."
            : error.message}
        </p>
      </div>
      <button className="button secondary" onClick={retry}>
        <RefreshCw size={15} />
        Retry
      </button>
    </div>
  );
}
export function Loading() {
  return (
    <div className="skeleton" role="status" aria-label="Loading content">
      <span />
      <span />
      <span />
    </div>
  );
}
export function WordReveal({ text }: { text: string }) {
  const reduced = useMotionPreference();
  return (
    <span className="word-reveal">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {text.split(" ").map((word, index) => (
          <span className="word-mask" key={index}>
            <motion.span
              initial={reduced ? false : { y: "110%", opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{
                duration: 0.6,
                delay: index * 0.07,
                ease: [0.22, 1, 0.36, 1],
              }}
            >
              {word}
            </motion.span>{" "}
          </span>
        ))}
      </span>
    </span>
  );
}
export function ProjectName({ id }: { id: string }) {
  const { data } = useProject(id);
  return (
    <>
      {data
        ? data.repository_url.replace("https://github.com/", "")
        : `Project ${id.slice(0, 8)}`}
    </>
  );
}
function RunRow({ run }: { run: Run }) {
  return (
    <tr>
      <td>
        <Link className="run-name" to={`/runs/${run.id}`}>
          <span className="repo-icon">
            <FolderGit2 size={17} />
          </span>
          <span>
            <strong>
              <ProjectName id={run.project_id} />
            </strong>
            <small>
              {run.branch || "Default branch"} <span>·</span>{" "}
              {run.commit_sha?.slice(0, 7) || run.id.slice(0, 7)}
            </small>
          </span>
        </Link>
      </td>
      <td>
        <Status value={run.status} />
      </td>
      <td>
        {run.total_tests ? (
          <>
            <strong>{run.passed_tests}</strong>
            <span className="muted"> / {run.total_tests} passed</span>
          </>
        ) : (
          <span className="muted">
            {run.testing_enabled ? "Awaiting tests" : "Discovery only"}
          </span>
        )}
      </td>
      <td className="mono">{duration(run)}</td>
      <td className="muted">{date(run.created_at)}</td>
      <td>
        <Link
          className="icon-button"
          aria-label={`View run ${run.id}`}
          to={`/runs/${run.id}`}
        >
          <ArrowUpRight size={18} />
        </Link>
      </td>
    </tr>
  );
}
export function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Repository / run</th>
            <th>Status</th>
            <th>Tests</th>
            <th>Duration</th>
            <th>Started</th>
            <th>
              <span className="sr-only">View</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
