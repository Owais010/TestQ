import * as Dialog from "@radix-ui/react-dialog";
import { useState, useEffect, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  GitBranch,
  Github,
  X,
  Check,
  ScanLine,
  FlaskConical,
} from "lucide-react";
import { api } from "../lib/api";
import type { Run } from "../lib/types";
export default function NewRun({
  open,
  onOpenChange,
  returnFocus,
  initialUrl = "",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  returnFocus: HTMLElement | null;
  initialUrl?: string;
}) {
  const [url, setUrl] = useState(initialUrl),
    [branch, setBranch] = useState(""),
    [testing, setTesting] = useState(true),
    [validation, setValidation] = useState("");

  useEffect(() => {
    if (open && initialUrl) {
      setUrl(initialUrl);
    }
  }, [open, initialUrl]);
  const navigate = useNavigate();
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      api<Run>("/api/test-runs", {
        method: "POST",
        body: JSON.stringify({
          repository_url: url.trim(),
          branch: branch.trim() || null,
          discover: true,
          testing_enabled: testing,
        }),
      }),
    onSuccess: (run) => {
      client.invalidateQueries({ queryKey: ["runs"] });
      onOpenChange(false);
      navigate(`/runs/${run.id}`);
      setUrl("");
      setBranch("");
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(url.trim())) {
      setValidation(
        "Enter a public GitHub repository URL, such as https://github.com/owner/repo.",
      );
      return;
    }
    setValidation("");
    mutation.mutate();
  }
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!mutation.isPending) {
          onOpenChange(value);
          mutation.reset();
          setValidation("");
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog-content"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (returnFocus?.isConnected) returnFocus.focus();
          }}
        >
          <div className="dialog-heading">
            <span className="eyebrow">A LITTLE MORE CERTAINTY</span>
            <Dialog.Close
              className="icon-button"
              aria-label="Close new run"
              disabled={mutation.isPending}
            >
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Title>Let’s take a closer look.</Dialog.Title>
          <Dialog.Description>
            Connect a public repository. TestQ will build it in an isolated
            sandbox and explore the running application.
          </Dialog.Description>
          <form onSubmit={submit}>
            <div style={{ marginBottom: "1.25rem", padding: "0.75rem 1rem", background: "rgba(255,255,255,0.03)", borderRadius: "8px", border: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
                <div>
                  <span className="eyebrow" style={{ fontSize: "0.7rem", color: "var(--accent)" }}>HACKATHON DEMO SHOWCASE</span>
                  <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "var(--muted)" }}>
                    Demo store with real intentional defects (BUG-001, BUG-002, BUG-003)
                  </p>
                </div>
                <button
                  type="button"
                  className="button secondary"
                  style={{ padding: "0.35rem 0.75rem", fontSize: "0.8rem", whiteSpace: "nowrap" }}
                  onClick={() => {
                    setUrl("https://github.com/demo/testq-store");
                    setBranch("");
                    setTesting(true);
                    setValidation("");
                  }}
                >
                  Load Demo
                </button>
              </div>
            </div>
            <label htmlFor="repo">GitHub repository</label>
            <div className="input-icon">
              <Github size={18} />
              <input
                id="repo"
                type="url"
                required
                autoFocus
                placeholder="https://github.com/you/project"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                aria-describedby={validation ? "run-error" : undefined}
              />
            </div>
            <label htmlFor="branch">
              Branch <span className="muted">(optional)</span>
            </label>
            <div className="input-icon">
              <GitBranch size={18} />
              <input
                id="branch"
                placeholder="Repository default"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              />
            </div>
            <fieldset>
              <legend>How deep should we go?</legend>
              <div className="mode-options">
                {[
                  {
                    value: false,
                    icon: ScanLine,
                    title: "Discover",
                    description: "Map pages, forms & endpoints",
                  },
                  {
                    value: true,
                    icon: FlaskConical,
                    title: "Discover & test",
                    description: "Run the available QA pipeline",
                  },
                ].map((mode) => (
                  <label
                    className={`mode-option ${testing === mode.value ? "chosen" : ""}`}
                    key={mode.title}
                  >
                    <input
                      type="radio"
                      name="mode"
                      checked={testing === mode.value}
                      onChange={() => setTesting(mode.value)}
                    />
                    <mode.icon size={22} />
                    <strong>{mode.title}</strong>
                    <span>{mode.description}</span>
                    {testing === mode.value && (
                      <Check className="mode-check" size={15} />
                    )}
                  </label>
                ))}
              </div>
            </fieldset>
            {(validation || mutation.error) && (
              <p className="form-error" role="alert" id="run-error">
                {validation || mutation.error?.message}
              </p>
            )}
            <div className="dialog-bottom">
              <span>
                <i className="live-dot" />
                Local execution. Your control.
              </span>
              <button
                className="button primary"
                disabled={mutation.isPending}
                type="submit"
              >
                {mutation.isPending ? "Starting…" : "Start run"}
                <ArrowUpRight size={17} />
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
