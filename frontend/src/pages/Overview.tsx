import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  GitBranch,
  ScanLine,
  ShieldCheck,
  Layers,
  Activity,
  Check,
  Command,
  FlaskConical,
} from "lucide-react";
import { Link } from "react-router-dom";
import { lazy, Suspense } from "react";
import { useRuns } from "../lib/api";
import { terminal } from "../lib/types";
import {
  Reveal,
  RunTable,
  Empty,
  Loading,
  ErrorState,
  WordReveal,
} from "../components/ui";
const Sculpture = lazy(() => import("../components/Sculpture"));
export default function Overview({ onNew }: { onNew: () => void }) {
  const query = useRuns();
  const runs = query.data?.runs || [];
  const active = runs.filter((r) => !terminal(r)).length;
  const tests = runs.reduce((sum, r) => sum + r.total_tests, 0);
  const passed = runs.reduce((sum, r) => sum + r.passed_tests, 0);
  return (
    <>
      <Reveal className="page-heading">
        <div>
          <div className="eyebrow">YOUR QUALITY WORKSPACE</div>
          <h1>
            <WordReveal text="A clearer picture." />
          </h1>
          <p>From the first commit to the last detail.</p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={17} />
          New test run
        </button>
      </Reveal>
      <Reveal className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">
            <span className="tiny-star">✳</span> BUILT FOR THE DETAILS
          </span>
          <h2>
            Ship with
            <br />
            <em>peace of mind.</em>
          </h2>
          <p>
            Go beyond “it works on my machine.”
            <br />
            Explore your app. Test the experience.
            <br />
            Keep the evidence.
          </p>
          <button className="text-link" onClick={onNew}>
            Put your project to the test <ArrowUpRight size={18} />
          </button>
          <div className="hero-foot">
            <span>
              <ShieldCheck size={14} />
              Isolated by design
            </span>
            <span>
              <span className="live-dot" />
              Entirely local
            </span>
          </div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <span className="art-index">FIG. 01 / PERSPECTIVE</span>
          <Suspense fallback={<div className="sculpture-fallback" />}>
            <Sculpture />
          </Suspense>
          <span className="art-caption">GOOD SOFTWARE. FROM EVERY ANGLE.</span>
          <span className="art-plus">+</span>
        </div>
      </Reveal>
      <Reveal className="stats-grid" delay={0.08}>
        {[
          {
            name: "Total runs",
            value: query.data?.total,
            icon: Layers,
            caption: "Across your workspace",
          },
          {
            name: "In progress",
            value: active,
            icon: Activity,
            caption: "In the latest 12 runs",
          },
          {
            name: "Tests executed",
            value: tests,
            icon: FlaskConical,
            caption: "In the latest 12 runs",
          },
          {
            name: "Pass rate",
            value: tests ? `${Math.round((passed / tests) * 100)}%` : "—",
            icon: ShieldCheck,
            caption: tests
              ? `${passed} of ${tests} tests passed`
              : "Waiting for test results",
          },
        ].map((item) => (
          <div className="stat-card" key={item.name}>
            <div>
              <span>{item.name}</span>
              <item.icon size={17} />
            </div>
            <strong>
              {query.isPending ? "—" : query.isError ? "—" : (item.value ?? 0)}
            </strong>
            <small>{item.caption}</small>
          </div>
        ))}
      </Reveal>
      <Reveal className="panel">
        <div className="section-heading">
          <div>
            <h2>
              Recent runs <span className="count">{runs.length}</span>
            </h2>
            <p>A living record of what you’ve put to the test.</p>
          </div>
          <Link className="text-link" to="/runs">
            View all runs
            <ArrowRight size={16} />
          </Link>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => query.refetch()} />
        ) : runs.length ? (
          <RunTable runs={runs.slice(0, 5)} />
        ) : (
          <Empty
            title="Your first run is a good place to start."
            text="Connect a repository. We’ll handle the build, browser, and details."
            action={onNew}
          />
        )}
      </Reveal>
      <Reveal className="workflow">
        <div className="section-heading">
          <div>
            <span className="eyebrow">LESS GUESSWORK. MORE CONTEXT.</span>
            <h2>A considered path to quality.</h2>
          </div>
          <span className="workflow-note">
            One repository. A complete perspective.
          </span>
        </div>
        <div className="workflow-grid">
          {[
            {
              icon: GitBranch,
              n: "01",
              title: "Bring your code",
              text: "A GitHub URL is all it takes. Your app builds in its own disposable environment.",
            },
            {
              icon: ScanLine,
              n: "02",
              title: "Meet your application",
              text: "A real browser discovers pages, forms, and the paths your users take.",
            },
            {
              icon: Check,
              n: "03",
              title: "See the whole story",
              text: "Review test results alongside screenshots, traces, and application logs.",
            },
          ].map((step) => (
            <div className="workflow-step" key={step.n}>
              <div>
                <step.icon size={24} />
                <span>{step.n}</span>
              </div>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </div>
          ))}
        </div>
      </Reveal>
      <footer className="page-footer">
        <span>Made for the moments before you ship.</span>
        <Link to="/welcome">
          The TestQ approach <Command size={13} />
        </Link>
      </footer>
    </>
  );
}
