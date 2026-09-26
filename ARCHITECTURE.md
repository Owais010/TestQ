# TestQ — Architecture Document

> **Independent AI QA Agent**
> *"Let AI build it. Let independent AI try to break it."*

---

## Current Phase 4.5 Hackathon Hardening (2026-09-25)

Phase 4.5 extends TestQ with lightweight, safe AI Failure Analysis, a controlled demo
e-commerce store with intentional defects, and an interactive real-time QA dashboard.
The core architectural rule remains strictly enforced: **AI reasons. Deterministic code executes.**
The AI has zero execution privileges.

### Complete Hackathon Architecture

```text
GitHub Repository (or Local Demo Store)
       ↓
Repository Analysis & Detection
       ↓
Docker Sandbox (Non-root UID 10001/10002, loopback isolation)
       ↓
Playwright Discovery (Pages, Forms, Inputs, Buttons, APIs)
       ↓
Application Map + Project Manifest
       ↓
AI Test Strategy (15 QA Categories)
       ↓
AI Test Generation (Whitelisted Actions & Assertions)
       ↓
Deterministic Execution (In-Sandbox Playwright / HTTPX)
       ↓
Real Intentional Bug Detection (e.g., broken cart checkout link, invalid quantity 0)
       ↓
AI Failure Analysis (Structured FailureAnalysis: title, severity, category, root cause, reproduction)
       ↓
SQLite Persistence (TestCases, TestResults, FailureAnalyses, Evidence)
       ↓
Interactive Real-Time Dashboard (/dashboard)
       ↓
Container & Workspace Cleanup (0 orphaned containers)
```

### AI Failure Analyzer Service (`backend/app/services/failure_analyzer.py`)

- **Untrusted Observations Boundary:** Passes test case details, executed steps, failed assertion details, HTTP status, and console observations as inert JSON data. System prompt commands the AI that application data has zero authority.
- **Controlled Structured Output:**
  - `title`: Short descriptive defect name.
  - `severity`: Controlled enum (`low`, `medium`, `high`, `critical`).
  - `category`: Controlled enum (`navigation`, `authentication`, `validation`, `input`, `UI`, `API`, `workflow`, `error_handling`, `unknown`).
  - `summary`: Concise failure explanation.
  - `likely_root_cause`: Technical hypothesis based on evidence without claiming absolute proof.
  - `reproduction_steps`: Ordered concrete steps to trigger the bug.
  - `evidence_references`: Linked screenshot and log filenames.
  - `confidence`: Calibrated score (0.0 to 1.0).
- **Graceful Non-Crashing Failure:** If Ollama is unavailable or times out, the test result remains recorded as FAIL/ERROR/TIMEOUT, a warning is logged, and the run finishes successfully.

### Controlled Demo Store (`demo/`)

A dedicated Node.js Express e-commerce application designed for repeatable, deterministic hackathon demonstrations:
- **Routes:** `/` (Home), `/products` (Catalog), `/login` (Auth), `/cart` (Cart), `/checkout` (Order), `/api/status`, `/api/products`, `/api/login`, `/api/checkout`.
- **BUG-001 (Validation):** Checkout accepts order with `quantity: 0` without error.
- **BUG-002 (Validation / Auth):** Login accepts invalid email without format validation.
- **BUG-003 (Navigation):** Cart "Proceed to Checkout" button navigates to broken route `/checkout-broken` (HTTP 404).

### Real-Time Dashboard (`/dashboard`)

- Self-contained, zero-install real-time dashboard served directly by the backend at `http://localhost:8000/dashboard`.
- Distinctly displays Baseline tests (`HOME-001`, `NAV-xxx`) and AI-generated tests (`AI-UI-xxx`).
- Displays high-visibility AI Bug Finding cards with severity glows, reproduction steps, likely root causes, and confidence badges.

---

## Historical Phase 4 implementation (verified 2026-09-25)

This section documents the Phase 4 AI Test Generation architecture, which builds on
and extends the Phase 3 deterministic execution foundation. The later full-product
architecture remains a roadmap: no runtime monitoring, static analysis, AI failure
analysis, or bug classification are implemented (Phases 5 and 6).

### AI Test Generation Architecture

```text
GitHub Repository
       ↓
Repository Analysis
       ↓
Docker Sandbox
       ↓
Playwright Discovery
       ↓
Application Map + Project Manifest
       ↓
PHASE 4: AI Test Planner / Generator
       ↓
STRICT STRUCTURED TEST SCHEMAS
       ↓
PHASE 3 DETERMINISTIC TEST EXECUTOR
       ↓
Playwright / HTTPX inside sandbox
       ↓
Evidence + Test Results
```

### Core Architectural Principle

**AI reasons. Deterministic code executes.**

The AI layer outputs structured data only. It NEVER executes shell commands, arbitrary Python,
arbitrary JavaScript, browser `evaluate`, Docker commands, or arbitrary HTTP requests.

### Free MVP & Provider Abstraction

- **100% Free to Run:** Uses local **Ollama** (`POST /api/generate`) as the V1/default provider.
- **Config Defaults:**
  - `AI_PROVIDER=ollama`
  - `OLLAMA_HOST=http://localhost:11434`
  - `AI_MODEL=qwen3:8b`
- **Extensible Base:** `backend/app/ai/base.py` defines `AIProvider` ABC with timeout, structured
  output validation, and explicit error taxonomy (`AIUnavailableError`, `AITimeoutError`,
  `AIInvalidOutputError`, `AISchemaValidationError`, `AIGenerationLimitError`).
- **No Paid APIs or Cloud Dependencies:** No OpenAI, Gemini, Groq, or Anthropic keys are required.
- **Network Isolation:** Untrusted repository code inside the Docker sandbox has loopback networking
  only and CANNOT reach the host Ollama service. Ollama runs on the host backend only.

### Prompt Injection Defense (Observation vs. Instruction)

Repository contents, HTML, page text, source files, READMEs, API responses, console messages, and
discovered application metadata are strictly treated as **untrusted observations**.
The system prompt explicitly commands the AI model that application content has zero authority
to alter execution rules, execute commands, or bypass testing limits.

### QA Test Matrix & Test Planning

- **`TestPlanner` (`backend/app/services/test_planner.py`):**
  Synthesizes a structured `TestStrategy` from the `ApplicationMap` and `ProjectManifest`.
  Restricted to controlled QA matrix categories:
  `navigation`, `authentication`, `forms`, `validation`, `inputs`, `buttons`, `selects`,
  `checkboxes`, `radio controls`, `api`, `error handling`, `boundary values`, `empty states`,
  `required fields`, `workflow`.
- **Target Restrictions:** Every strategy item must target a discovered route or relative path.
  External URLs (`http://`, `https://`, `//`) are strictly stripped and rejected.
- **Planner Limits:** Capped at `AI_MAX_STRATEGY_ITEMS=15` with bounded retry attempts (`AI_MAX_RETRIES=2`).

### Structured Test Generation & Validation

- **`TestGenerator` (`backend/app/services/test_generator.py`):**
  Translates the `TestStrategy`, `ApplicationMap`, and manifest into structured `TestDefinition` objects.
- **Namespaced Identifiers:** AI tests use distinct namespaces (`AI-UI-xxx` for UI tests, `AI-API-xxx` for API tests)
  to prevent collision with deterministic baseline tests (`HOME-001`, `NAV-xxx`, `UI-xxx`, `API-xxx`).
- **Whitelisted Actions Only:** Only deterministic Phase 3 actions are allowed:
  `goto`, `click`, `fill`, `select`, `check`, `uncheck`, `wait`.
- **Whitelisted Assertions Only:**
  - UI: `page_loaded`, `url_matches`, `text_visible`, `element_visible`, `element_hidden`, `input_value`, `http_status`.
  - API: `status_code`, `response_time`, `content_type`, `json_field_present`, `json_value`.
- **Strict Validation Pipeline:**
  `Ollama JSON → Pydantic AITestGenerationOutput → Individual validate_test_definition() → Semantic/Security Checks → Deduplication → Limits`.
- **Deduplication:** AI tests are deterministically deduplicated against baseline tests and among AI tests
  by action/step and request signatures.
- **Limits:** Capped at `AI_MAX_GENERATED_TESTS=20` and overall `MAX_TESTS_PER_RUN=50`.

### Combined Test Suite & Persistence

- **Baseline + AI:** Deterministic baseline tests from `BaselineTestGenerator` remain intact and provide
  reproducible foundational coverage. AI tests augment this suite.
- **Persistence:** Test cases are stored in SQLite with a `source` column (`source="baseline"` vs. `source="ai"`).
- **Distinguishable Failures:** Ollama unavailability or timeouts log an AI warning and allow the pipeline
  to continue executing baseline tests to completion. AI errors are NEVER classified as application bugs.

---

## Historical Phase 3 implementation (verified 2026-09-25)

This section supersedes the historical Phase 2 and Phase 1 snapshots below. The later
full-product architecture remains a roadmap: no AI test generation, bug classification,
reports, or autonomous browser actions are implemented.

### Deterministic Test Engine Pipeline

Phase 3 extends the pipeline between discovery and sandbox cleanup:

```text
Application Map
      ↓
Deterministic Test Definitions (HOME, NAV, UI, API)
      ↓
Schema Validation (Pydantic TestDefinition)
      ↓
Controlled Test Executor (Limits & Isolation)
      ↓
In-Sandbox Playwright / HTTPX (Non-root UID 10002)
      ↓
Assertions (page_loaded, url_matches, element_visible, status_code, json_value, etc.)
      ↓
PASS / FAIL / ERROR / TIMEOUT / CANCELLED
      ↓
Evidence (Screenshots, execution JSON, console, network)
      ↓
SQLite (TestCases, TestResults, Evidence linking)
```

### State Machine Transitions

- **Discovery-Only Runs (`discover: true, testing_enabled: false`):**
  `READY → DISCOVERING → DISCOVERY_COMPLETE` (terminal).
- **Testing-Enabled Runs (`discover: true, testing_enabled: true`):**
  `READY → DISCOVERING → TESTING → COMPLETED` (terminal).
- **Strict Configuration Enforcement:**
  Requests with `testing_enabled: true` and `discover: false` are strictly rejected with HTTP 400.
- State transitions are strictly enforced: `DISCOVERING` transitions directly to `TESTING` if testing is enabled, or to `DISCOVERY_COMPLETE` if disabled. `DISCOVERY_COMPLETE → TESTING` is NOT permitted.
- Any active state can transition to `FAILED` or `CANCELLED`.
- Pipeline cleanup occurs after testing finishes and evidence is exported, before the run commits its terminal state (`COMPLETED`, `FAILED`, or `CANCELLED`).

### In-Sandbox Runners & Execution

- `testq_browser.test_runner`: Executes UI test steps (`goto`, `click`, `fill`, `select`, `check`, `uncheck`, `wait`) and UI assertions (`page_loaded`, `url_matches`, `text_visible`, `element_visible`, `element_hidden`, `input_value`, `http_status`) using Playwright inside the sandbox.
- Selector resolution requires single-element matches (`locator.count() == 1`). If multiple elements match, candidate selectors from the application map are tried in priority order; ambiguous matches fail cleanly without guessing.
- `testq_browser.api_runner`: Executes API test requests using HTTPX inside the sandbox against loopback `127.0.0.1:<port>`. Evaluates assertions (`status_code`, `response_time`, `content_type`, `json_field_present`, `json_value`).
- Both runners run as UID 10002 inside the container, write isolated JSON and screenshot artifacts under `/tmp/testq_run_<id>/`, and exit with clean structured JSON results.
- No arbitrary code evaluation (`eval`, shell execution, arbitrary python/js) is permitted or implemented.

### Host Orchestration & Test Limits

- `BaselineTestGenerator`: Synthesizes deterministic test definitions directly from the Phase 2 `ApplicationMap`:
  - `HOME-001`: Root page smoke test (page load, URL match, element presence).
  - `NAV-xxx`: Navigation tests verifying same-origin links load the expected target paths.
  - `UI-xxx`: Form interaction tests exercising discovered buttons, inputs, and controls.
  - `API-xxx`: API endpoint checks verifying status code and response structure.
  No AI or LLM generation is involved; test generation is 100% deterministic and reproducible.
- `TestExecutor`: Host dispatcher that iterates through test cases, enforces step limits (`MAX_STEPS_PER_TEST=20`), test suite size limits (`MAX_TESTS_PER_RUN=50`), action timeouts (`TEST_ACTION_TIMEOUT=5s`), and per-test execution timeouts (`TEST_TIMEOUT=30s`).
- `PlaywrightRunner` and `ApiTester`: Host orchestrators invoking in-sandbox execution via `SandboxManager.execute()`, transferring evidence archives, extracting and validating artifacts.
- Results are recorded as `PASS`, `FAIL`, `ERROR`, `TIMEOUT`, or `CANCELLED`.
- Cancellation gracefully stops the running test and sets subsequent tests to `CANCELLED`.

### Evidence and SQLite Persistence

- `TestCase`: Persisted schema defining the test suite for a run.
- `TestResult`: Persisted execution outcomes including status, duration, error details, and step counts.
- `Evidence`: Test evidence (screenshots, test result JSON, trace artifacts) is linked via `test_result_id` foreign key and stored under `evidence/<run_id>/testing/<test_result_id>/`.
- REST APIs:
  - `GET /api/test-runs/{id}/test-cases`: Retrieve generated test definitions.
  - `GET /api/test-runs/{id}/test-results`: Retrieve test execution results and outcomes.
  - `GET /api/test-runs/{id}/evidence?test_result_id={test_result_id}`: Filter evidence by test result.

### Limits and Strict Boundaries

- **NO AI Test Generation in Phase 3:** All Phase 3 tests are generated deterministically by `BaselineTestGenerator` from the application map.
- **NO AI Bug Classification:** Failures remain pure assertion failures or runtime errors; no bug reports, severities, or AI classifications are created.
- **Strict Sandbox Isolation:** Testing runs in the existing isolated container with loopback networking only. No host ports or external access.

---

## Historical Phase 2 contract (verified 2026-09-25)

This section supersedes the historical Phase 1 snapshot below. The later full-product
architecture remains a roadmap: no AI test generation, bug classification, reports,
or autonomous browser actions are implemented.

`Pipeline.run()` retains its existing resource ownership and cleanup. For new API
runs (`discover: true` by default), successful health checking publishes live READY,
then DISCOVERING. `DiscoveryService` runs the TestQ-owned Python runner inside the
same container against `http://127.0.0.1:<internal-port>`. DISCOVERY_COMPLETE is only
committed after evidence export, log retention, and cleanup. `discover: false` retains
Phase 1's final READY behavior. Discovery progress does not mark testing/report stages
complete. Cancellation and whole-run deadlines still terminate the container and
prevent later success transitions.

### Controlled browser and bounded discovery

Both images contain pinned Python Playwright 1.63.0, Chromium and its OS dependencies,
independent of the target repository. The target runs as UID 10001; the browser runner
uses UID 10002, isolated Python imports, root-owned `/opt/testq`, and a private
`/discovery/<session_id>` directory. No application port is published. Runtime has
loopback only. Browser requests are further restricted to the exact target origin;
external HTTP requests/navigation and WebSockets are blocked, service workers disabled.

Chromium's own sandbox stays enabled. The Playwright seccomp profile permits namespace
creation, adds clone3 ENOSYS fallback, and allows the chroot syscall needed inside
Chromium's user namespace. No container capability is added: ALL remain dropped,
along with no-new-privileges, no host mounts/socket, no privileged mode, two CPUs,
2 GiB memory and 256 PIDs. Browser-enabled containers use private 256 MiB shared memory.
The chroot requirement follows [Chromium's namespace sandbox implementation](https://chromium.googlesource.com/chromium/src/+/lkgr/sandbox/linux/services/credentials.cc).

`backend/testq_browser` separates schemas, URL/frontier policies, browser lifecycle,
DOM inspection, observers, artifacts, and orchestration. Breadth-first navigation starts
at `/`, strips query/fragment variants, normalizes paths, rejects credentialled/external
URLs, and caps pages/depth. Defaults: 12 pages, depth 3, navigation 8s, action 3s,
session 60s. The host execution supervisor allows 15s for runner finalization, bounded
by the existing whole-run deadline. Failed routes keep their real HTTP status;
404 is `http_error`, not successful navigation. Individual navigation failures normally
allow remaining pages to be inspected. Browser launch failure fails discovery.

DOM inspection stores links, forms, buttons, inputs, selects/options, checkbox/radio
state, labels and selector candidates. Candidate preference is test ID, role/name,
ID, name, stable attribute, CSS fallback. Candidates are observed, not guaranteed
unique or tested for future interactions. No form submission, filling or clicking occurs.
Network records contain method, sanitized URL/path, resource type, status and duration;
console, browser errors and failed requests remain unclassified observations.

### Evidence and SQLite persistence

`DiscoverySession` stores a versioned typed application map as reassigned JSON, including
pages/elements/endpoints/observations. `Evidence` stores run/session/page context, kind,
relative path, size, SHA-256 and media type. Existing SQLite records are preserved by
idempotent additive columns and create-if-missing tables; no database recreation or
PostgreSQL dependency is introduced.

Each completed page checkpoints its map. Before container removal, the host reads
bounded regular files via Docker archive APIs (without extracting archive paths),
validates context/size/hash/type, atomically writes exports, verifies them again and
persists metadata. Artifacts live under `evidence/<run_id>/discovery/<session_id>/`.
Application stdout/stderr are copied to SQLite and linked in a bounded application-log
artifact. Cancellation/hard timeout exports the last completed checkpoint from the
stopped container. An in-flight page may be incomplete.

Screenshots are fixed 1280x720 with form controls/iframes/private regions masked.
Per-page sanitized Playwright traces retain action timing and navigation outcomes;
DOM snapshots, source files, response bodies, network headers and raw console trace
events are omitted. Separate console/network/error JSON retains bounded observations.
Artifacts default to 8 MiB each and 64 MiB per session; trace/screenshot counts are
bounded by max pages. Exceeding a budget reports failure and retains available data.
Read-only discovery/evidence endpoints verify downloaded artifact integrity and context.

### Limits and threat model

- This is anonymous, path-based link discovery. Hash routers, query-dependent pages,
  authenticated flows, click-only navigation, exhaustive SPA exploration and delayed
  background activity beyond the short observation window are not covered.
- External CDN assets/APIs are blocked; pages can render differently from production.
  Setup still requires network access for dependency installation. No production API
  is intentionally targeted by discovery.
- Headers, cookies, request/response bodies and input values are not recorded. Known
  secret patterns and URL queries are redacted. Arbitrary secrets rendered as text or
  custom console messages cannot be reliably recognized; screenshots can contain other
  visible page content. Do not inject production credentials or datasets into test apps.
- Traces intentionally omit DOM/network payloads; they are not full-fidelity replays.
  The application map is observational evidence, not proof that the application is correct.
- Container isolation shares the host kernel. Browser namespace syscalls expand the
  container syscall surface; keep Docker/Chromium patched. Untrusted application logs
  are not tamper-proof. Same-container separate users protect runner files, not a VM boundary.
- Backend/daemon crashes can lose artifacts not yet exported. Startup recovery cleans
  orphan resources; it does not resume browser discovery or recover unfinished traces.
  A single backend process remains required.

## Historical Phase 1 contract (verified 2026-09-24)

The sections below describe the full target product. Only the execution foundation
and the existing Ollama adapter are implemented; browser discovery, AI testing,
reports, and dashboard remain future work. This section takes precedence over
illustrative interfaces/state examples later in the target architecture.

### Run ownership and execution

`api/test_runs.py` schedules `worker/pipeline.py` with a per-run `RunControl`.
The current supported deployment is one API worker process. The control carries a
thread-safe cancellation event, monotonic whole-run deadline, and completion signal.
Synchronous operations run in joined threads; cancelling the asyncio task signals
execution and waits for the blocking operation to exit instead of abandoning it.

The manager records the generated container name before its create request, and
handles partial create/copy failure. The pipeline's nested `finally` blocks stop
execution, export logs, remove every owned container, and remove its reserved clone
workspace even when an earlier operation fails. Removal failures are retried and
reported, not suppressed. Containers carry managed/run labels for recovery.

Repository install/build/start commands run only inside Docker. Commands use detached
Docker exec with stdout/stderr files and execution polling. A command timeout or
cancellation kills the whole container and its descendants. Files remain readable
from the stopped container until export/removal. `DOCKER_TIMEOUT` bounds commands;
`RUN_TIMEOUT` bounds the entire run including cloning. Docker requests themselves
have a transport timeout. Cleanup may extend past the execution deadline.
Images must be provisioned before a run; obsolete images are rejected by label.

### State and cancellation

Phase 1 follows `QUEUED → CLONING → ANALYZING → BUILDING → STARTING → READY`.
Each active state can fail or be cancelled. READY is published after successful
health checking and cleanup, with `finished_at` populated and live sandbox metadata
cleared. It does not promise a still-running preview. Invalid transitions raise;
updates use a compare-and-set condition on the old status and cancellation flag.
Progress JSON is copied/reassigned and committed rather than mutated in place.

Cancellation persists `cancellation_requested` before signalling the worker. The
worker stops active execution, exports logs, cleans up, and finally commits CANCELLED.
The API returns 202 if cleanup exceeds its five-second response wait; clients poll
until terminal. Completed Phase 1 runs reject cancellation. Startup recovers
unfinished runs and labelled orphan containers. Recovery is single-instance only;
a distributed/durable job queue is not part of Phase 1.

### Sandbox security and networking

Both images run repository commands as UID/GID 10001, with all capabilities dropped,
no-new-privileges, no privileged mode, no host mounts/socket, CPU/memory/PID limits,
and an additional container lifetime watchdog. Sources are copied as the application
user, with escaping symlinks and special files rejected; copy size is capped at 256 MiB.

Install/build have bridge networking for dependency downloads and build-time assets.
Before startup, every Docker network is disconnected. Runtime has loopback only;
health checking uses an in-container curl request to the selected port, without
following redirects. The pipeline publishes no host ports. Optional low-level port
mappings are loopback-bound. A future same-container browser can use this same local
application URL; no browser tooling has been installed.

Setup network access is not registry-allowlisted, so dependency scripts can make
outbound requests then. Runtime applications requiring external APIs or databases
are unsupported by this default. Docker is not a VM security boundary. Host/daemon
outage can prevent immediate removal; failures remain visible, and the watchdog
bounds container execution but cannot itself remove containers. Unlabelled legacy
containers are not automatically adopted. Logs not yet exported may be lost on an
abrupt host/backend crash.

### Configuration, storage, logs and detection

The root `.env`, database, workspace and evidence paths are independent of cwd.
SQLite uses `sqlite+aiosqlite`; legacy synchronous URLs are normalized. Existing
Phase 1 databases receive an idempotent additive cancellation-column migration.
Databases are not automatically relocated. Persisted tables remain projects,
test_runs and logs; the broader data model below is future scope.

Command/application stdout and stderr are retained separately, bounded to 10 MiB per
file, then copied into SQLite logs in 64 KiB records before container removal. They
are retrievable through the existing logs endpoint. They are untrusted observations,
not tamper-proof evidence. No screenshots/traces/evidence APIs or live streaming exist.
Build dependencies are installed with development settings; application startup sets
NODE_ENV=production. Health accepts 2xx/3xx/401/403, but rejects 404 and 5xx.

An omitted branch resolves to remote HEAD. Detection supports existing root apps and
one unambiguous standalone nested app within two directory levels. A root testq.json
can select project_dir and port. Common literal custom-port patterns are recognized;
Vite gets a strict selected port. Shared workspace/multi-service orchestration and
arbitrary executable configuration discovery remain unsupported.

### Verification and Phase 2 boundary

87 tests passed with real Docker enabled on 2026-09-24 (10 Docker cases), plus the
original local Express integration script. The suite covers success, failures,
cancellation, enforced timeouts, cleanup, state/progress, logs, configuration,
network restrictions, non-root execution and SQLite migration. Three existing
schema collection warnings remain. Real pipeline tests clone local Git fixtures,
including a non-main default branch; no new public-GitHub integration result is claimed.

Phase 2 should extend the live portion of Pipeline.run after health succeeds and
before cleanup. It must not attach to a finished READY run. Phase 2 is not started.

---
## 1. System Overview

TestQ is a modular platform that accepts a GitHub repository URL, securely builds and runs the application inside an isolated Docker sandbox, discovers its functionality through real browser and API interaction, generates and executes adversarial tests, collects runtime evidence, uses AI to analyze failures, and produces actionable QA reports.

### Core Principle

```
AI reasoning → Structured plan → Controlled executor → Real execution → Evidence → AI analysis
```

The AI **reasons** about testing strategy and interprets evidence. Deterministic application code **executes** all test actions. The AI never directly runs shell commands or arbitrary code.

---

## 2. High-Level Architecture

```
                    ┌──────────────────────┐
                    │     Next.js UI        │
                    │  (TypeScript/Tailwind)│
                    └──────────┬───────────┘
                               │ REST / WebSocket
                               ▼
                    ┌──────────────────────┐
                    │      FastAPI          │
                    │  API + Orchestrator   │
                    └───────┬────┬─────────┘
                            │    │
                 ┌──────────┘    └──────────┐
                 ▼                          ▼
          ┌──────────────┐           ┌─────────────┐
          │   GitHub      │           │   SQLite     │
          │   Service     │           │   Database   │
          └──────┬───────┘           └─────────────┘
                 ▼
          ┌──────────────┐
          │   Worker      │
          │   Process     │
          └──────┬───────┘
                 ▼
          ┌────────────────────┐
          │   Docker Sandbox   │
          │  (Disposable)      │
          └─────────┬──────────┘
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
      Playwright   HTTPX   Static Tools
          │         │          │
          └─────────┼──────────┘
                    ▼
             Evidence Store
                    │
                    ▼
             AI QA Analyzer
                    │
                    ▼
              Bug Classifier
                    │
                    ▼
               QA Report
```

---

## 3. Technology Stack

| Layer          | Technology                        | Responsibility                                                   |
| -------------- | --------------------------------- | ---------------------------------------------------------------- |
| **Frontend**   | Next.js + TypeScript + Tailwind   | Repository input, run progress, dashboard, bugs, evidence viewer |
| **Backend**    | Python 3.13 + FastAPI             | REST API, orchestration, state transitions, report APIs          |
| **Worker**     | Python worker process             | Long-running test jobs and sandbox lifecycle                     |
| **Execution**  | Docker                            | Isolation, resource limits, cleanup                              |
| **Browser**    | Playwright                        | UI interaction, screenshots, network and console evidence        |
| **API Test**   | HTTPX / Playwright API            | Endpoint test execution                                         |
| **Static**     | ESLint, Semgrep, npm audit        | Code/dependency checks                                          |
| **Database**   | SQLite (→ PostgreSQL later)       | Projects, runs, tests, bugs, evidence metadata                  |
| **AI**         | Provider abstraction (Ollama default, OpenAI optional) | Test strategy, analysis, classification, reporting     |

---

## 4. Subsystem Responsibilities

### 4.1 Frontend (`frontend/`)

The Next.js dashboard serves as the user-facing interface.

**Pages / Views:**
- **Home / Landing** — Repository URL input, branch selection, "Start Testing" / "Try Demo"
- **Test Run Progress** — Real-time pipeline stages with live status updates
- **Dashboard Overview** — QA score, test summary, bug counts by severity
- **Bugs** — Filterable/sortable bug list with classification, severity, confidence
- **Test Cases** — Generated and executed tests with pass/fail status
- **Project Analysis** — Detected framework, dependencies, routes, APIs
- **Evidence** — Screenshots, traces, console logs, network logs per test
- **Logs** — Runtime logs from build, startup, and testing phases
- **Recommendations** — AI-generated remediation suggestions

**Data Source:** All data consumed via REST API from the FastAPI backend. No hardcoded fake data.

---

### 4.2 Backend (`backend/`)

The FastAPI application provides the REST API, orchestrates the QA pipeline, and manages state.

#### 4.2.1 API Layer (`backend/app/api/`)

| Endpoint                            | Method | Purpose                          |
| ----------------------------------- | ------ | -------------------------------- |
| `/api/projects`                     | POST   | Create project from repository   |
| `/api/projects/{id}`                | GET    | Get project details              |
| `/api/test-runs`                    | POST   | Start a new test run             |
| `/api/test-runs/{id}`               | GET    | Get run status and summary       |
| `/api/test-runs/{id}/cancel`        | POST   | Cancel an active run             |
| `/api/test-runs/{id}/tests`         | GET    | List generated/executed tests    |
| `/api/test-runs/{id}/bugs`          | GET    | List classified issues           |
| `/api/test-runs/{id}/logs`          | GET    | Read runtime logs                |
| `/api/test-runs/{id}/evidence`      | GET    | List evidence artifacts          |
| `/api/test-runs/{id}/report`        | GET    | Get final QA report              |

All request/response contracts defined with **Pydantic models**.

#### 4.2.2 Service Modules

Each service is a focused Python module with a clear interface:

```
backend/app/services/
├── github_service.py          # Clone repos, resolve branches
├── repository_analyzer.py     # Coordinate detection
├── project_detector.py        # Framework/language detection
├── build_manager.py           # Install → build → start pipeline
├── sandbox_manager.py         # Docker container lifecycle
├── application_runner.py      # Start app, detect port, health check
├── port_detector.py           # Find active ports in sandbox
├── health_checker.py          # Verify application is reachable
├── discovery_service.py       # Playwright-based app exploration
├── test_planner.py            # QA strategy generation
├── test_generator.py          # AI-driven structured test generation
├── test_executor.py           # Deterministic test runner dispatcher
├── playwright_runner.py       # UI test execution via Playwright
├── api_tester.py              # API endpoint testing via HTTPX
├── static_analyzer.py         # ESLint, Semgrep, npm audit runner
├── runtime_monitor.py         # stdout/stderr/crash monitoring
├── evidence_manager.py        # Collect, store, link evidence
├── ai_analyzer.py             # AI failure analysis
├── bug_classifier.py          # Classification + severity + confidence
├── reproduction_engine.py     # Replay tests for confirmation
├── bug_deduplicator.py        # Cluster related failures
└── report_generator.py        # Generate final QA report
```

---

### 4.3 Sandbox (`sandbox/`)

The sandbox is the **security boundary** between TestQ and untrusted repository code.

**Principle:** Repository code NEVER executes on the TestQ host.

```
sandbox/
├── Dockerfile.sandbox         # Base image for test-run containers
├── docker/
│   ├── node.Dockerfile        # Node.js/React/Next.js base
│   └── python.Dockerfile      # Python/FastAPI base
└── runner/
    └── entrypoint.sh          # Controlled entrypoint script
```

**SandboxManager Interface:**

```python
class SandboxManager:
    async def create(config: SandboxConfig) -> Sandbox
    async def copy_repo(sandbox: Sandbox, repo_path: Path) -> None
    async def execute(sandbox: Sandbox, command: str, timeout: int) -> ExecutionResult
    async def stream_logs(sandbox: Sandbox) -> AsyncIterator[LogEntry]
    async def get_port_mapping(sandbox: Sandbox, port: int) -> str
    async def stop(sandbox: Sandbox) -> None
    async def destroy(sandbox: Sandbox) -> None
```

**Security Controls:**

| Control             | Implementation                                      |
| ------------------- | --------------------------------------------------- |
| CPU limit           | `--cpus=2`                                          |
| Memory limit        | `--memory=2g`                                       |
| Timeout             | Wall-clock kill after configurable max (e.g., 600s) |
| Filesystem          | Isolated `/workspace`, no host mounts               |
| Network             | Docker bridge network, restricted where possible    |
| Privileges          | `--security-opt=no-new-privileges`, no `--privileged` |
| Cleanup             | Container removed after every run                   |
| Docker socket       | Never exposed to sandbox                            |
| Secrets             | Not injected into sandbox by default                |

---

### 4.4 Worker Architecture

Long-running test pipelines run in a background worker, not inside the API request lifecycle.

```
API Request (POST /api/test-runs)
       │
       ▼
  Create DB record (status: QUEUED)
       │
       ▼
  Dispatch to Worker
       │
       ▼
  Worker executes pipeline:
       CLONING → ANALYZING → BUILDING → STARTING →
       READY → TESTING → ANALYZING_FAILURES → COMPLETED
       │
       ▼
  Update DB with results at each state transition
```

**Initial implementation:** In-process background tasks (asyncio).
**Future:** Redis + Celery/ARQ for horizontal scaling.

---

### 4.5 AI Provider Abstraction (`backend/app/ai/`)

```
AIProvider (abstract)
├── OllamaProvider     ← V1 default (free, local)
├── OpenAIProvider     ← optional, future
├── GeminiProvider     ← optional, future
└── GroqProvider       ← optional, future
```

**V1 Constraint:** No paid API keys required. Ollama runs locally and is the default provider. Other providers can be added but are not needed for the MVP.

Only one provider needs to be active. The abstraction ensures provider-independence.

**AI is used for specialized roles:**

| Role                  | Input                              | Output                              |
| --------------------- | ---------------------------------- | ----------------------------------- |
| Repository Analyst    | Project files + metadata           | Project manifest / capability map   |
| Test Strategist       | Manifest + discovery               | Risk areas + test priorities        |
| Test Generator        | Strategy + app map                 | Structured executable test cases    |
| Failure Analyzer      | Expected + actual + evidence       | Failure explanation                 |
| Bug Classifier        | Failure analysis + evidence        | Classification + severity + conf.   |
| Report Writer         | Structured findings                | Developer-readable QA report        |

**All AI inputs and outputs use structured JSON schemas.** The AI never receives arbitrary execution privileges.

---

## 5. Data Model

```
projects
  │
  └── test_runs
        │
        ├── test_cases
        │      └── test_results
        │             └── evidence
        │
        ├── bugs
        │      └── bug_evidence
        │
        └── logs
```

### Entity Details

| Table          | Key Fields                                                                |
| -------------- | ------------------------------------------------------------------------- |
| `projects`     | id, repository_url, default_branch, detected_framework, created_at       |
| `test_runs`    | id, project_id, commit, status, started_at, finished_at, summary         |
| `test_cases`   | id, run_id, type (ui/api/static), title, steps (JSON), priority          |
| `test_results` | id, test_case_id, status, expected, actual, duration_ms, error           |
| `bugs`         | id, run_id, title, classification, severity, confidence, root_cause      |
| `evidence`     | id, result_id, kind (screenshot/trace/console/network/log), path, meta   |
| `logs`         | id, run_id, source, timestamp, level, message                            |

**Storage:** SQLite initially. Schema designed for easy migration to PostgreSQL.

---

## 6. Test Run State Machine

```
QUEUED → CLONING → ANALYZING → BUILDING → STARTING → READY → TESTING → ANALYZING_FAILURES → COMPLETED
                                                                                                  │
Any state ─── error ──→ FAILED                                                                    │
                          │                                                                       │
                          └── BUILD_FAILED (special case: build errors reported honestly)          │
```

| State                | Meaning                                          |
| -------------------- | ------------------------------------------------ |
| `QUEUED`             | Run created, waiting for worker                  |
| `CLONING`            | Repository being fetched                         |
| `ANALYZING`          | Project structure being detected                 |
| `BUILDING`           | Dependencies and build steps running             |
| `STARTING`           | Application process starting                     |
| `READY`              | Application health check passed                  |
| `TESTING`            | Tests executing                                  |
| `ANALYZING_FAILURES` | AI interpreting evidence                          |
| `COMPLETED`          | QA report available                              |
| `FAILED`             | Run could not proceed                            |

**Critical rule:** If build fails → status = `FAILED` with sub-state `BUILD_FAILED`. Never pretend testing succeeded.

---

## 7. Evidence System

Every test result can produce an evidence package:

```
evidence/{run_id}/{test_case_id}/
├── screenshot.png           # Visual failure state
├── trace.zip                # Playwright trace for action replay
├── console.json             # Browser console log entries
├── network.json             # HTTP requests/responses
├── application.log          # Backend stdout/stderr
└── metadata.json            # Timestamps, test context, environment
```

**Separation of concerns:**
- **OBSERVED** — Raw facts: HTTP 500, console error, screenshot
- **AI ANALYSIS** — Interpretation: "Possible null handling issue"

AI conclusions are **never** stored as observed facts.

---

## 8. Test Engine Architecture

### 8.1 Structured Test Definition

AI generates tests as structured JSON, not arbitrary code:

```json
{
  "id": "TEST-017",
  "type": "ui",
  "title": "Login with empty password",
  "priority": "high",
  "steps": [
    {"action": "goto", "target": "/login"},
    {"action": "fill", "target": "#email", "value": "test@example.com"},
    {"action": "fill", "target": "#password", "value": ""},
    {"action": "click", "target": "button[type=submit]"}
  ],
  "expected": {
    "type": "validation_message",
    "condition": "visible"
  }
}
```

### 8.2 Test Categories (QA Matrix)

| Category      | Examples                                              |
| ------------- | ----------------------------------------------------- |
| Happy path    | Valid input, normal CRUD                               |
| Empty         | Blank fields, empty payloads                          |
| Invalid       | Malformed email, invalid IDs                          |
| Missing       | Missing required parameters or headers                |
| Type abuse    | String where number expected                          |
| Boundary      | 0, 1, max length, large values                        |
| Duplicate     | Existing email, duplicate records                     |
| State         | Expired session, stale page                           |
| Authorization | Direct access to protected routes                     |
| Error handling| Backend failures, timeout behavior                    |

### 8.3 Deterministic Executor

The executor interprets the structured test definition. It:
- Validates the test schema before execution
- Rejects unsupported or unsafe actions
- Runs each step sequentially
- Captures evidence at each step
- Records timing and results
- Can replay tests for reproduction

---

## 9. Failure Classification

```
Test Failure
    │
    ▼
┌─────────────────────────┐
│  AI Failure Analysis    │
│  (receives evidence)    │
└──────────┬──────────────┘
           │
    ┌──────┼──────┬──────────────┐
    ▼      ▼      ▼              ▼
Confirmed  Possible  Test       Environment
   Bug      Bug     Failure     Failure
```

**AI output structure:**

```json
{
  "classification": "confirmed_bug",
  "severity": "high",
  "confidence": 0.96,
  "title": "...",
  "expected": "...",
  "actual": "...",
  "root_cause": "...",
  "reproduction_steps": ["..."],
  "recommendation": "...",
  "evidence_ids": ["..."]
}
```

---

## 10. Bug Lifecycle

```
Detection → Reproduction → Deduplication → Classification → Report
```

1. **Detection** — Test failure observed with evidence
2. **Reproduction** — Replay test 2-3 times to confirm
3. **Deduplication** — Cluster by endpoint, exception, error signature
4. **Classification** — AI assigns category, severity, confidence
5. **Report** — Include in final QA report with full evidence

---

## 11. Directory Structure

```
TestQ/
│
├── frontend/                    # Next.js application
│   ├── app/                     # App router pages
│   ├── components/              # Reusable UI components
│   ├── lib/                     # API client, utilities
│   ├── public/                  # Static assets
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.ts
│
├── backend/                     # FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Configuration
│   │   ├── database.py          # SQLite/DB setup
│   │   ├── api/                 # Route handlers
│   │   │   ├── projects.py
│   │   │   ├── test_runs.py
│   │   │   └── evidence.py
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── project.py
│   │   │   ├── test_run.py
│   │   │   ├── test_case.py
│   │   │   ├── test_result.py
│   │   │   ├── bug.py
│   │   │   ├── evidence.py
│   │   │   └── log.py
│   │   ├── schemas/             # Pydantic request/response
│   │   │   ├── project.py
│   │   │   ├── test_run.py
│   │   │   ├── test_case.py
│   │   │   ├── bug.py
│   │   │   └── evidence.py
│   │   ├── services/            # Business logic modules
│   │   │   ├── github_service.py
│   │   │   ├── repository_analyzer.py
│   │   │   ├── project_detector.py
│   │   │   ├── build_manager.py
│   │   │   ├── sandbox_manager.py
│   │   │   ├── application_runner.py
│   │   │   ├── port_detector.py
│   │   │   ├── health_checker.py
│   │   │   ├── discovery_service.py
│   │   │   ├── test_planner.py
│   │   │   ├── test_generator.py
│   │   │   ├── test_executor.py
│   │   │   ├── playwright_runner.py
│   │   │   ├── api_tester.py
│   │   │   ├── static_analyzer.py
│   │   │   ├── runtime_monitor.py
│   │   │   ├── evidence_manager.py
│   │   │   ├── ai_analyzer.py
│   │   │   ├── bug_classifier.py
│   │   │   ├── reproduction_engine.py
│   │   │   ├── bug_deduplicator.py
│   │   │   └── report_generator.py
│   │   ├── ai/                  # AI provider abstraction
│   │   │   ├── base.py
│   │   │   ├── openai_provider.py
│   │   │   └── prompts/
│   │   └── worker/              # Background task runner
│   │       ├── orchestrator.py
│   │       └── pipeline.py
│   ├── tests/                   # Backend test suite
│   ├── requirements.txt
│   └── pyproject.toml
│
├── sandbox/                     # Docker sandbox definitions
│   ├── Dockerfile.node          # Node.js sandbox image
│   ├── Dockerfile.python        # Python sandbox image
│   └── scripts/
│       └── entrypoint.sh
│
├── demo/                        # Demo vulnerable application
│   └── vulnerable-app/
│       ├── package.json
│       ├── src/
│       └── README.md
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md → (this file, symlinked or at root)
│   └── API.md
│
├── docker-compose.yml           # Full stack orchestration
├── IMPLEMENTATION_PLAN.md       # Implementation tracking
├── ARCHITECTURE.md              # This file
├── README.md                    # Project README
├── .env.example                 # Environment variable template
└── .gitignore
```

---

## 12. Data Flow — Complete Test Run

```
1.  User submits GitHub URL + branch via frontend
2.  Frontend → POST /api/test-runs → Backend
3.  Backend creates project (if new) and test_run record (QUEUED)
4.  Backend dispatches to Worker
5.  Worker: CLONING — git clone into temp directory
6.  Worker: ANALYZING — project_detector scans files
7.  Worker: BUILDING — sandbox_manager creates Docker container
         → execute install command
         → execute build command
         → if failure: status=FAILED, preserve logs, STOP
8.  Worker: STARTING — execute start command in sandbox
         → port_detector finds active port
         → health_checker verifies HTTP response
         → if failure: status=FAILED, preserve logs, STOP
9.  Worker: READY — app is running
10. Worker: TESTING
         a. discovery_service → Playwright explores app → app_map
         b. test_planner → AI creates test strategy
         c. test_generator → AI produces structured test cases
         d. test_executor → dispatches to:
              - playwright_runner (UI tests)
              - api_tester (API tests)
              - static_analyzer (lint/audit)
         e. runtime_monitor → collects crashes, errors, logs
         f. evidence_manager → stores screenshots, traces, logs
11. Worker: ANALYZING_FAILURES
         a. ai_analyzer → interprets evidence per failure
         b. bug_classifier → assigns classification/severity
         c. reproduction_engine → replays important failures
         d. bug_deduplicator → clusters related issues
12. Worker: COMPLETED
         a. report_generator → builds final QA report
         b. All data persisted to database
13. Frontend polls GET /api/test-runs/{id} for progress
14. Frontend renders dashboard with real data
```

---

## 13. Security Architecture

TestQ executes **untrusted code by design**. Security is a first-class architectural concern.

### Threat Model

| Threat                         | Mitigation                                    |
| ------------------------------ | --------------------------------------------- |
| Malicious repo code            | All execution in disposable Docker containers |
| Resource exhaustion             | CPU, memory, and time limits                  |
| Host filesystem access          | No host mounts in sandbox                     |
| Container escape                | No privileged mode, no Docker socket          |
| Network abuse                   | Restricted networking where possible          |
| Secret leakage                  | No secrets injected into sandbox              |
| Persistent contamination        | Container destroyed after every run           |
| AI prompt injection             | Structured JSON schemas, not free-form        |

### Defense Layers

1. **Network isolation** — Sandbox containers on isolated Docker network
2. **Process isolation** — Linux namespaces via Docker
3. **Resource limits** — CPU, memory, PID limits enforced
4. **Time limits** — Wall-clock timeout kills everything
5. **Filesystem isolation** — Temporary workspace, no host mounts
6. **Privilege restriction** — `no-new-privileges`, non-root where possible
7. **Automatic cleanup** — Container + volumes removed after run
8. **Input validation** — All API inputs validated via Pydantic
9. **Structured AI** — AI outputs validated against JSON schemas

---

## 14. Configuration

All secrets and configuration via environment variables:

```bash
# Database
DATABASE_URL=sqlite+aiosqlite:///./testq.db

# AI Provider (V1: Ollama is default, no paid API needed)
AI_PROVIDER=ollama           # ollama | openai | gemini | groq
OLLAMA_HOST=http://localhost:11434
AI_MODEL=llama3.1            # or any Ollama-compatible model
# OPENAI_API_KEY=sk-...      # Only if using OpenAI (optional)

# Docker
DOCKER_TIMEOUT=600           # Max seconds per test run
DOCKER_CPU_LIMIT=2
DOCKER_MEMORY_LIMIT=2g

# GitHub
GITHUB_TOKEN=ghp_...         # Optional, for private repos

# Application
HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=3000
EVIDENCE_DIR=./evidence
LOG_LEVEL=INFO
```

---

## 15. API Contract Example

### Create Test Run

**Request:**
```json
POST /api/test-runs
{
  "repository_url": "https://github.com/user/project",
  "branch": "main"
}
```

**Response:**
```json
{
  "id": "run_abc123",
  "project_id": "proj_xyz",
  "status": "QUEUED",
  "repository_url": "https://github.com/user/project",
  "branch": "main",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Get Test Run (with progress)

```json
GET /api/test-runs/run_abc123
{
  "id": "run_abc123",
  "status": "TESTING",
  "progress": {
    "cloning": "completed",
    "analyzing": "completed",
    "building": "completed",
    "starting": "completed",
    "discovery": "completed",
    "test_generation": "completed",
    "ui_testing": "in_progress",
    "api_testing": "pending",
    "static_analysis": "pending",
    "failure_analysis": "pending",
    "report": "pending"
  },
  "summary": {
    "framework": "nextjs",
    "total_tests": 41,
    "completed_tests": 18,
    "passed": 14,
    "failed": 4
  }
}
```

---

*This document defines the target architecture. Implementation proceeds phase-by-phase as tracked in `IMPLEMENTATION_PLAN.md`.*

## Phase 2 verification record — 2026-09-25

The complete suite passed 125 tests with both Docker and public-app flags enabled:
87 preserved Phase 1 tests and 38 Phase 2 tests (28 non-Docker, 10 real Docker).
No tests were skipped; three pre-existing Pydantic schema collection warnings remain.
Both images built and launched sandboxed Chromium as UID 10002. Fixture discovery,
HTTP 404 recording, navigation/session limits, failure cleanup and cancellation
through the API passed. The public Heroku Express sample also completed discovery.
Screenshots and JSON were inspected after removal, and the sanitized trace ZIP was
inspected for retained action events and empty network payload. The trace viewer UI
was not separately validated. No TestQ-managed containers remained. Detailed evidence
paths and commit/run IDs are in IMPLEMENTATION_PLAN.md. No later phase was started.
