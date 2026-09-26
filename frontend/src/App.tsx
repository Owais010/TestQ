import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { NavLink, Route, Routes, useLocation, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion, useScroll, useSpring } from "motion/react";
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  LayoutDashboard,
  FolderGit2,
  Play,
  Settings2,
  Plus,
  Menu,
  X,
  Monitor,
  ExternalLink,
} from "lucide-react";
import Overview from "./pages/Overview";
import { Projects, Runs } from "./pages/Runs";
const RunDetail = lazy(() => import("./pages/RunDetail"));
const Welcome = lazy(() => import("./pages/Welcome"));
import NewRun from "./components/NewRun";
import { api, base } from "./lib/api";
import { ErrorState, Loading } from "./components/ui";
class Boundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <ErrorState error={this.state.error} retry={() => location.reload()} />
    ) : (
      this.props.children
    );
  }
}
export default function App() {
  const returnFocus = useRef<HTMLElement | null>(null);
  const sidebar = useRef<HTMLElement | null>(null);
  const [narrow, setNarrow] = useState(
    () => window.matchMedia("(max-width:800px)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(max-width:800px)");
    const change = () => {
      setNarrow(media.matches);
      if (!media.matches) setMobile(false);
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const [open, setOpen] = useState(false),
    [mobile, setMobile] = useState(false);
  const location = useLocation();
  useEffect(() => {
    if (!mobile) return;
    const previous = document.activeElement as HTMLElement;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const items = () =>
      Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>(
          "a, button:not(:disabled)",
        ) || [],
      ).filter((el) => el.getClientRects().length);
    items()[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const nodes = items();
      const first = nodes[0],
        last = nodes.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      document.body.style.overflow = original;
      if (previous.isConnected) previous.focus();
    };
  }, [mobile]);
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string; ai_model?: string; ai_status?: string }>("/health"),
    refetchInterval: 15000,
    retry: 0,
  });
  const [motionOff, setMotionOff] = useState(
    () => localStorage.getItem("testq-reduce-motion") === "true",
  );
  useEffect(() => {
    document.documentElement.dataset.motion = motionOff ? "off" : "on";
    localStorage.setItem("testq-reduce-motion", String(motionOff));
    window.dispatchEvent(new Event("testq-motion-change"));
  }, [motionOff]);
  useEffect(() => {
    setMobile(false);
    window.scrollTo({ top: 0, behavior: "instant" });
    document.title = `${["/", "/welcome"].includes(location.pathname) ? "A little more certainty" : location.pathname.startsWith("/runs/") ? "Run details" : location.pathname === "/runs" ? "Test runs" : location.pathname === "/projects" ? "Projects" : location.pathname === "/settings" ? "Preferences" : "Overview"} · TestQ`;
  }, [location.pathname]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        returnFocus.current = document.activeElement as HTMLElement;
        setMobile(false);
        setOpen(true);
      }
      if (e.key === "Escape") setMobile(false);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const [presetUrl, setPresetUrl] = useState("");
  const start = (preset?: unknown) => {
    setPresetUrl(typeof preset === "string" ? preset : "");
    returnFocus.current = mobile
      ? document.querySelector<HTMLElement>('[aria-label="Open navigation"]')
      : (document.activeElement as HTMLElement);
    setMobile(false);
    setOpen(true);
  };
  const welcome = location.pathname === "/" || location.pathname === "/welcome";
  return (
    <Boundary>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {!motionOff && (
        <motion.div className="scroll-progress" style={{ scaleX }} />
      )}
      {welcome ? (
        <main id="main">
          <Suspense fallback={<Loading />}>
            <Welcome onNew={start} />
          </Suspense>
        </main>
      ) : (
        <div className="app-shell">
          {mobile && (
            <button
              className="sidebar-backdrop"
              aria-label="Close navigation"
              onClick={() => setMobile(false)}
            />
          )}
          <aside
            ref={sidebar}
            className={`sidebar ${mobile ? "is-open" : ""}`}
            inert={narrow && !mobile}
            role={mobile ? "dialog" : undefined}
            aria-modal={mobile ? true : undefined}
            aria-label="Workspace navigation"
          >
            <div className="sidebar-brand">
              <Link className="brand" to="/">
                <img src="/favicon.svg" alt="" />
                TestQ
              </Link>
              <button
                className="icon-button mobile-only"
                aria-label="Close navigation"
                onClick={() => setMobile(false)}
              >
                <X size={20} />
              </button>
            </div>
            <Link className="workspace-switch" to="/settings">
              <span className="workspace-avatar">W</span>
              <span>
                <strong>My workspace</strong>
                <small>Local environment</small>
              </span>
              <ChevronRight size={14} />
            </Link>
            <span className="nav-label">WORKSPACE</span>
            <nav className="side-nav">
              {[
                { to: "/dashboard", icon: LayoutDashboard, label: "Overview" },
                { to: "/runs", icon: Play, label: "Test runs" },
                { to: "/projects", icon: FolderGit2, label: "Projects" },
              ].map((item) => (
                <NavLink end={item.to === "/"} to={item.to} key={item.to}>
                  <item.icon size={18} />
                  {item.label}
                  <span className="nav-active-dot" />
                </NavLink>
              ))}
            </nav>
            <div className="sidebar-divider" />
            <nav className="side-nav">
              <NavLink to="/settings">
                <Settings2 size={18} />
                Preferences
              </NavLink>
              <Link to="/welcome">
                <BookOpen size={18} />
                The TestQ approach
                <ArrowUpRight size={14} />
              </Link>
            </nav>
            <div className="sidebar-bottom">
              <div className="sidebar-note">
                <span className="mini-mark">✳</span>
                <h3>
                  Small details.
                  <br />
                  Better releases.
                </h3>
                <p>
                  Your next insight is
                  <br />
                  one run away.
                </p>
                <button onClick={start}>
                  Start a new run
                  <Plus size={16} />
                </button>
              </div>
              <div className="local-status" style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.25rem", padding: "0.5rem 0.75rem", borderRadius: "6px", background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%" }}>
                  <i className={`live-dot ${health.isError ? "offline" : ""}`} />
                  <span style={{ fontSize: "0.8rem", fontWeight: 500 }}>
                    {health.isPending
                      ? "Connecting…"
                      : health.isError
                        ? "Backend offline"
                        : "Backend online"}
                  </span>
                  <Monitor size={13} style={{ marginLeft: "auto", opacity: 0.6 }} />
                </div>
                {health.data && (
                  <span style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
                    AI Model: <strong style={{ color: "var(--text)" }}>{(health.data as any).ai_model || "qwen3:8b"}</strong> ({(health.data as any).ai_status || "READY"})
                  </span>
                )}
              </div>
              <div className="profile">
                <span className="avatar">Y</span>
                <div>
                  <strong>Your workspace</strong>
                  <small>Local · Personal</small>
                </div>
              </div>
            </div>
          </aside>
          <div className="workspace-main" inert={mobile}>
            <header className="topbar">
              <div>
                <button
                  className="icon-button mobile-only"
                  aria-label="Open navigation"
                  aria-expanded={mobile}
                  onClick={() => setMobile(true)}
                >
                  <Menu size={21} />
                </button>
                <span>Workspace</span>
                <ChevronRight size={13} />
                <strong>
                  {location.pathname.startsWith("/runs/")
                    ? "Run details"
                    : location.pathname === "/runs"
                      ? "Test runs"
                      : location.pathname === "/projects"
                        ? "Projects"
                        : location.pathname === "/settings"
                          ? "Preferences"
                          : "Overview"}
                </strong>
              </div>
              <div>
                <span className="environment">
                  <i
                    className={`live-dot ${health.isError ? "offline" : ""}`}
                  />
                  {health.isError ? "Disconnected" : "Local environment"}
                </span>
                <button
                  className="quick-add"
                  aria-label="Start a new test run"
                  onClick={start}
                >
                  <Plus size={18} />
                </button>
                <span className="avatar small">Y</span>
              </div>
            </header>
            <main id="main" className="main-content">
              <Suspense fallback={<Loading />}>
                <Routes>
                  <Route
                    path="/dashboard"
                    element={<Overview onNew={start} />}
                  />
                  <Route path="/runs" element={<Runs onNew={start} />} />
                  <Route path="/runs/:id" element={<RunDetail />} />
                  <Route
                    path="/projects"
                    element={<Projects onNew={start} />}
                  />
                  <Route
                    path="/settings"
                    element={
                      <>
                        <div className="page-heading">
                          <div>
                            <span className="eyebrow">
                              MAKE YOURSELF AT HOME
                            </span>
                            <h1>A few preferences.</h1>
                            <p>A quieter workspace, on your terms.</p>
                          </div>
                        </div>
                        <section className="panel compact preferences">
                          <h2>Appearance & motion</h2>
                          <div className="preference-row">
                            <div>
                              <strong>Reduce decorative motion</strong>
                              <p>
                                Keep transitions and the 3D illustration still.
                                System preferences are also respected.
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              aria-label="Reduce decorative motion"
                              checked={motionOff}
                              onChange={(e) => setMotionOff(e.target.checked)}
                            />
                          </div>
                          <h2>Connection</h2>
                          <div className="preference-row">
                            <div>
                              <strong>Backend API</strong>
                              <p>
                                {base ||
                                  "Same-origin proxy → http://127.0.0.1:8000"}
                              </p>
                              <small>
                                Configure VITE_API_BASE_URL at build time to use
                                another backend.
                              </small>
                            </div>
                            <span
                              className={`status ${health.isError ? "bad" : "good"}`}
                            >
                              {health.isError
                                ? "Offline"
                                : health.isPending
                                  ? "Connecting"
                                  : "Connected"}
                            </span>
                          </div>
                          <a
                            className="text-link"
                            href={`${base || "http://127.0.0.1:8000"}/docs`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open backend API documentation
                            <ExternalLink size={16} />
                          </a>
                        </section>
                      </>
                    }
                  />
                  <Route
                    path="*"
                    element={
                      <div className="not-found">
                        <span className="eyebrow">
                          404 / A LITTLE OFF TRACK
                        </span>
                        <h1>
                          This page took
                          <br />
                          <em>a different path.</em>
                        </h1>
                        <Link className="button primary" to="/dashboard">
                          Back to your workspace
                          <ArrowUpRight size={17} />
                        </Link>
                      </div>
                    }
                  />
                </Routes>
              </Suspense>
            </main>
          </div>
        </div>
      )}
      <NewRun
        open={open}
        onOpenChange={setOpen}
        returnFocus={returnFocus.current}
        initialUrl={presetUrl}
      />
    </Boundary>
  );
}
