import { useState, type PointerEvent } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";
import {
  ArrowUpRight,
  FileSearch,
  GitBranch,
  Layers,
  Pause,
  Play,
} from "lucide-react";
import { Reveal } from "./ui";
import { useMotionPreference } from "../lib/motion";

const features = [
  "Real browser discovery",
  "Isolated execution",
  "Retained evidence",
  "Local-first workflow",
];

function EvidenceStack() {
  const reduced = useMotionPreference();
  const x = useMotionValue(0),
    y = useMotionValue(0);
  const rotateX = useSpring(x, { stiffness: 130, damping: 22 });
  const rotateY = useSpring(y, { stiffness: 130, damping: 22 });
  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduced || event.pointerType !== "mouse") return;
    const rect = event.currentTarget.getBoundingClientRect();
    x.set((0.5 - (event.clientY - rect.top) / rect.height) * 12);
    y.set(((event.clientX - rect.left) / rect.width - 0.5) * 14);
  }
  return (
    <div
      className="evidence-stage"
      onPointerMove={move}
      onPointerLeave={() => {
        x.set(0);
        y.set(0);
      }}
    >
      <motion.div
        className="evidence-stack"
        style={{
          rotateX: reduced ? 0 : rotateX,
          rotateY: reduced ? 0 : rotateY,
        }}
      >
        <div className="evidence-sheet sheet-back" aria-hidden="true" />
        <div className="evidence-sheet sheet-middle" aria-hidden="true" />
        <div className="evidence-sheet sheet-front">
          <span className="eyebrow">THE ANATOMY OF A RUN</span>
          <FileSearch size={34} strokeWidth={1.3} />
          <h3>A trail you can follow.</h3>
          <div>
            <span>01</span> Application map <Layers size={16} />
          </div>
          <div>
            <span>02</span> Screenshots & traces <FileSearch size={16} />
          </div>
          <div>
            <span>03</span> Execution journal <GitBranch size={16} />
          </div>
          <small>Illustration of retained run artifacts</small>
        </div>
      </motion.div>
    </div>
  );
}

export default function WelcomeDetails({ onNew }: { onNew: () => void }) {
  const [paused, setPaused] = useState(false);
  const reduced = useMotionPreference();
  return (
    <>
      <section className="feature-ribbon" aria-label="TestQ capabilities">
        <div className="ribbon-window">
          <div
            className="ribbon-track"
            style={{
              animationPlayState: paused || reduced ? "paused" : "running",
            }}
          >
            {[0, 1].map((copy) => (
              <div
                className="ribbon-group"
                key={copy}
                aria-hidden={copy === 1 ? true : undefined}
              >
                {features.map((feature) => (
                  <span key={feature}>
                    <i aria-hidden="true">✳</i>
                    {feature}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
        <button
          className="icon-button"
          aria-label={
            paused ? "Resume feature animation" : "Pause feature animation"
          }
          aria-pressed={paused}
          disabled={Boolean(reduced)}
          onClick={() => setPaused(!paused)}
        >
          {paused || reduced ? <Play size={16} /> : <Pause size={16} />}
        </button>
      </section>
      <section className="welcome-story">
        <Reveal className="story-copy">
          <span className="eyebrow">FROM REPOSITORY TO PERSPECTIVE</span>
          <h2>
            Less wondering.
            <br />
            <em className="hover-ink">More understanding.</em>
          </h2>
          <p>
            Start with a public GitHub repository. TestQ prepares an isolated
            environment, starts the application, and opens it in a real browser.
          </p>
          <p>
            Discovery maps the pages, controls and requests it observes. Choose
            Discover & test to continue through the available testing pipeline,
            then review the evidence in your workspace.
          </p>
          <button className="text-link" onClick={onNew}>
            Bring your repository <ArrowUpRight size={17} />
          </button>
        </Reveal>
        <Reveal>
          <EvidenceStack />
        </Reveal>
      </section>
      <section className="welcome-process">
        <Reveal>
          <span className="eyebrow">ONE CONNECTED WORKFLOW</span>
          <h2>
            From the first URL
            <br />
            <em className="hover-ink">to the finer details.</em>
          </h2>
        </Reveal>
        <div className="process-cards">
          {[
            [
              "01",
              "Bring the source.",
              "Paste a public GitHub URL and optionally choose a branch. Select discovery alone or discovery with testing.",
            ],
            [
              "02",
              "See the application.",
              "Follow build and startup progress, then inspect the pages, forms and endpoints the browser discovers.",
            ],
            [
              "03",
              "Keep the context.",
              "Review results alongside screenshots, traces and application logs. Export retained artifacts for a closer look.",
            ],
          ].map(([number, title, text], i) => (
            <Reveal key={number} delay={i * 0.09}>
              <article className="process-card">
                <span className="process-number">{number}</span>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="welcome-faq">
        <Reveal>
          <span className="eyebrow">A FEW GOOD QUESTIONS</span>
          <h2>
            Before you
            <br />
            <em className="hover-ink">take a closer look.</em>
          </h2>
        </Reveal>
        <Reveal className="faq-list">
          {[
            [
              "What is the difference between discovery and testing?",
              "Discovery records the application's pages, controls, requests and browser observations. Testing executes the available checks. Completing discovery alone is not a verdict that an application has passed QA.",
            ],
            [
              "What stays after the sandbox is removed?",
              "Exported evidence stays associated with the run: screenshots, traces and recorded logs where available. Open the run's Evidence and Logs tabs to inspect what was retained.",
            ],
            [
              "Does TestQ need a paid cloud service?",
              "The runtime is designed for local execution with Docker and a controlled browser. The backend's optional AI capabilities use the configured local Ollama provider; availability depends on your local setup.",
            ],
            [
              "Will every repository work?",
              "Projects need a supported application setup that can build and start in the sandbox. Missing environment variables, unavailable dependencies or unsupported layouts can stop a run. Progress and logs show the recorded failure reason.",
            ],
          ].map(([question, answer]) => (
            <details key={question}>
              <summary>
                {question}
                <span aria-hidden="true">+</span>
              </summary>
              <p>{answer}</p>
            </details>
          ))}
        </Reveal>
      </section>
    </>
  );
}
