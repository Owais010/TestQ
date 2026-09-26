import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ArrowRight,
  ShieldCheck,
  ScanLine,
  Layers,
} from "lucide-react";
import { lazy, Suspense } from "react";
import { Reveal } from "../components/ui";
import WelcomeDetails from "../components/WelcomeDetails";
const Sculpture = lazy(() => import("../components/Sculpture"));
export default function Welcome({ onNew }: { onNew: (presetUrl?: string) => void }) {
  return (
    <div className="welcome">
      <nav>
        <Link className="brand" to="/">
          <img src="/favicon.svg" alt="" />
          TestQ<span>QUALITY, CONSIDERED.</span>
        </Link>
        <Link className="button secondary" to="/dashboard">
          Open workspace
          <ArrowUpRight size={16} />
        </Link>
      </nav>
      <section className="welcome-hero">
        <Reveal className="welcome-copy">
          <span className="eyebrow">
            A SECOND LOOK MAKES ALL THE DIFFERENCE.
          </span>
          <h1>
            You build the idea.
            <br />
            We explore
            <br />
            <em>the possibilities.</em>
          </h1>
          <p>
            A local-first workspace to discover, test, and understand your
            application. Less guesswork between a good idea and a great release.
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
            <button className="button primary" onClick={() => onNew()}>
              Test your application
              <ArrowUpRight size={18} />
            </button>
            <button
              className="button secondary"
              style={{ border: "1px solid rgba(255,255,255,0.2)", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
              onClick={() => onNew("https://github.com/demo/testq-store")}
            >
              Try Demo
              <ArrowUpRight size={18} />
            </button>
          </div>
          <a href="#approach" className="text-link">
            Find your perspective <ArrowRight size={16} />
          </a>
        </Reveal>
        <div className="welcome-art">
          <Suspense fallback={null}>
            <Sculpture />
          </Suspense>
          <span className="eyebrow">
            MOVE YOUR CURSOR. CHANGE YOUR PERSPECTIVE.
          </span>
        </div>
      </section>
      <section className="welcome-approach" id="approach">
        <Reveal>
          <span className="eyebrow">THOUGHTFUL BY DESIGN</span>
          <h2>
            Confidence isn’t a feeling.
            <br />
            <em>It’s something you can see.</em>
          </h2>
        </Reveal>
        <div className="workflow-grid">
          {[
            {
              icon: ShieldCheck,
              title: "Your code stays in your control.",
              text: "Disposable sandboxes. Local execution. A clear boundary between your application and your machine.",
            },
            {
              icon: ScanLine,
              title: "A real browser. A real perspective.",
              text: "See your application as it runs. Discover its routes, forms, interactions, and observed requests.",
            },
            {
              icon: Layers,
              title: "Every result has a story.",
              text: "Follow the screenshots, traces, and logs behind a result. Make the next decision with context.",
            },
          ].map((item, i) => (
            <Reveal className="workflow-step" key={item.title} delay={i * 0.1}>
              <item.icon size={27} />
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <WelcomeDetails onNew={() => onNew()} />
      <Reveal className="welcome-cta">
        <span className="eyebrow">YOUR NEXT RELEASE STARTS HERE</span>
        <h2>
          A little more certainty.
          <br />
          <em>A lot more possibility.</em>
        </h2>
        <button onClick={() => onNew()} className="button primary">
          Let’s take a closer look
          <ArrowUpRight size={17} />
        </button>
      </Reveal>
      <footer className="page-footer">
        <Link to="/" className="brand">
          TestQ<span>Independent by design.</span>
        </Link>
        <span>Built to look a little closer.</span>
      </footer>
    </div>
  );
}
