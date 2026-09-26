# TestQ — Autonomous AI-Powered QA Engineering Agent

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Sandboxed-2496ED.svg)](https://www.docker.com/)

TestQ is an autonomous, truthful, end-to-end AI QA engineering agent that clones, builds, and executes web applications inside disposable, security-hardened Docker sandboxes. It combines deterministic headless Playwright crawler discovery with local LLM test planning and test generation (Ollama `qwen3:8b`), executes UI and API test cases deterministically, captures visual evidence, and generates root-cause failure analyses for detected defects.

### Core Architectural Principle
> **AI reasons. Deterministic code executes.**  
> Untrusted LLM output never executes raw code directly. Test synthesis is strictly validated through Pydantic schemas, and all test executions are deterministically carried out via Playwright and HTTPX inside network-isolated containers.


## Setup

Requirements: Python 3.11+, Git, and running Docker Desktop with Linux containers.
Run these commands from the repository root (PowerShell):

```powershell
python -m venv backend/venv
backend/venv/Scripts/Activate.ps1
python -m pip install -r backend/requirements.txt
# Only if .env does not already exist:
Copy-Item .env.example .env

docker build -f sandbox/Dockerfile.node -t testq-sandbox-node:latest .
docker build -f sandbox/Dockerfile.python -t testq-sandbox-python:latest .
python backend/run.py
```

Rebuild both images after upgrading from the original Phase 1 images. The pipeline
checks their hardening label and fails with instructions if they are missing or
outdated; image provisioning is outside the bounded repository run.

`backend/run.py` uses `HOST` and `BACKEND_PORT` from settings. It can also be invoked
by absolute path from another directory. Default API: http://127.0.0.1:8000/docs.
Run **one backend process**, without `--workers` or development reload during runs.
The cancellation registry is in-process; this version is not a distributed worker.

## Configuration and existing databases

The root `.env` is loaded independently of the working directory. Relative database,
workspace, and evidence paths resolve against the repository root:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./testq.db
WORKSPACES_DIR=./workspaces
EVIDENCE_DIR=./evidence
DOCKER_TIMEOUT=600
RUN_TIMEOUT=900
DOCKER_API_TIMEOUT=15
HOST=127.0.0.1
BACKEND_PORT=8000
```

`DOCKER_TIMEOUT` bounds each install/build command; `RUN_TIMEOUT` bounds the whole
run, including clone and startup. Docker requests have a separate transport timeout.
Cleanup can extend past the execution deadline while resources are removed.

Legacy `sqlite:///` URLs are normalized to `sqlite+aiosqlite:///`. Startup adds the
`cancellation_requested` and `discovery_enabled` columns to existing databases
without deleting data, and creates discovery/evidence tables. Existing runs keep
discovery disabled; new API requests default to `discover: true`.
No database is automatically moved: if an older database lives at `backend/testq.db`,
point `DATABASE_URL` at that file before startup. These are additive migrations,
not a general migration framework.

## Execution behavior

`POST /api/test-runs` accepts a public GitHub `repository_url` and optional `branch`.
Omitting the branch uses the repository's default branch; the resolved branch and
commit are persisted after cloning. Explicit branches remain supported.

```text
QUEUED → CLONING → ANALYZING → BUILDING → STARTING → READY
                               ↘ FAILED / CANCELLED
```

The pipeline installs and builds with development dependencies available. Runtime
uses `NODE_ENV=production`. Health is checked from inside the container using its
loopback application port. HTTP 2xx/3xx and authentication challenges (401/403)
indicate readiness; 404 and 5xx do not. Redirects are not followed by the sandbox probe.

With `discover: true`, the live run continues `READY → DISCOVERING → DISCOVERY_COMPLETE`.
Evidence is exported and verified before the sandbox and clone are removed. The final
state means discovery completed, not QA testing completed. With `discover: false`,
the original Phase 1 behavior remains: READY is published after cleanup. Neither
mode provides a persistent hosted preview.

Cancellation first persists `cancellation_requested`, then signals the live worker.
The worker stops execution, retains logs, removes resources, and commits `CANCELLED`.
The endpoint returns 200 when cleanup finishes within five seconds, or 202 while
cancellation is still in progress; poll the run endpoint until terminal. Finished
runs reject cancellation. Cancellation cannot be overwritten by a later READY update.

On restart, unfinished runs are recovered using their labelled containers and run
workspaces, then marked FAILED or CANCELLED. Recovery refuses to claim success if
Docker cleanup fails. Do not run multiple TestQ instances against this database/Docker
host. Unlabelled containers from older versions are not automatically removed.

## Sandbox boundaries

- Non-root UID/GID 10001 for repository install, build, and application execution.
- No privileged mode, Docker socket, or host mounts; all Linux capabilities dropped.
- `no-new-privileges`, two CPUs, 2 GiB memory/no extra swap, 256 PIDs by default.
- Ownership recorded before Docker creation; partial creation/copy failures are cleaned.
- Command timeout and cancellation kill the whole container, including child processes.
- A container lifetime watchdog provides an additional bound if the worker disappears.
- Setup/build use bridge networking for package downloads and build-time assets.
- Before application startup, all network interfaces except loopback are disconnected.
  Runtime has no public-internet, host-service, or other-container connectivity.
- The pipeline publishes no host ports. Explicit SandboxManager port mappings, used
  by the legacy integration script during setup, bind only to 127.0.0.1.
- Cleanup is always the default; there is no automatic debug preservation mode.

Setup networking is **not an outbound allowlist**: dependency lifecycle scripts run
with network access during setup. This is a remaining isolation limitation. Runtime
apps that require external APIs/databases fail honestly; multi-service networking and
network exceptions are not implemented. Docker shares a kernel and is not a VM boundary.
A daemon/host outage can prevent immediate removal; cleanup retries and reports the
error instead of pretending success. The watchdog stops execution but does not remove
the container by itself. Abrupt process/host loss may lose logs not yet exported.

## Detection scope

Supports Next.js, React/Vite, generic Node.js with a start script, and FastAPI.
Detection prefers the repository root, then one unambiguous nested app within two
levels (maximum 100 directories). Ambiguity is an error. For an explicit selection:

```json
{"project_dir": "apps/web", "port": 4321}
```

Place this in `testq.json` at the repository root. Paths cannot escape the repository.
Ports are taken from start/preview arguments or common literal Node server patterns;
Vite gets an explicit strict port. Arbitrary executable config is never evaluated on
the host. Root package-manager workspaces/shared dependencies and multiple services
are not orchestrated; select a standalone app or expect a clear build failure.

## Logs and API

Application and command stdout/stderr go to separate bounded container files, then
are exported to SQLite before removal. `GET /api/test-runs/{id}/logs?source=application`
retrieves retained application output after the sandbox is gone. Records identify
the stream and are split into 64 KiB chunks. Each output file is limited to 10 MiB;
excess output can terminate its writer. Container log archives are read without
extracting untrusted paths. Repository copies are capped at 256 MiB.

Logs reflect untrusted application output; they are not tamper-proof evidence.
Discovery adds retained screenshots, sanitized traces, maps, and evidence APIs.
Live log streaming is not implemented.

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Backend availability |
| `/api/projects` | POST | Create/find project |
| `/api/projects/{id}` | GET | Project metadata |
| `/api/test-runs` | POST | Start a run |
| `/api/test-runs/{id}` | GET | Run status/progress |
| `/api/test-runs/{id}/cancel` | POST | Request and signal cancellation |
| `/api/test-runs/{id}/logs` | GET | Retained command/application logs |
| `/api/test-runs/{id}/discovery` | GET | Typed application map and raw observations |
| `/api/test-runs/{id}/test-cases` | GET | Generated deterministic test cases |
| `/api/test-runs/{id}/test-results` | GET | Test execution results and assertion outcomes |
| `/api/test-runs/{id}/evidence` | GET | Evidence metadata and download links (supports `?test_result_id=`) |
| `/api/test-runs/{id}/evidence/{evidence_id}` | GET | Integrity-checked artifact download |

## Verification

```powershell
cd backend
python -m pytest tests -q
$env:TESTQ_DOCKER_TESTS = '1'
$env:TESTQ_PUBLIC_APP_TEST = '1'
python -m pytest tests -q
python tests/test_integration_local.py
```

Verified 2026-09-25: **225 tests passed with Docker enabled**, including **24 real Docker
cases** (with 1 optional local Ollama test skipped when local Ollama is offline), with 0 pytest
collection warnings. Tests cover real Git fixture cloning/default branch, Node/FastAPI readiness,
install/build/startup failure, API cancellation, command timeout, whole-run deadline, copy failure,
network isolation, log retention, state/progress, configuration, migration, browser discovery,
deterministic test generation, in-sandbox Playwright UI action execution (goto, click, fill, select, check, uncheck, wait),
all 7 UI assertions for PASS and FAIL, in-sandbox HTTPX API testing, assertion evaluation
(status_code, response_time, content_type, json_field_present, json_value), path boundary protections,
evidence extraction, post-test container cleanup, Ollama provider abstraction, prompt injection defense,
Test Planner strategy generation, Test Generator schema validation, deterministic deduplication,
limits enforcement, and full real Docker end-to-end pipeline execution with AI-generated tests.
Docker tests are opt-in; without the environment flag, Docker-dependent tests are skipped.

See [ARCHITECTURE.md](ARCHITECTURE.md) for current behavior and future design, and
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the verification gate. Later phases
(Phase 5 runtime monitoring/static analysis and Phase 6 AI failure analysis/bug classification) are NOT enabled.

## Deterministic browser discovery

New runs default to discovery (`discover: true`). Example request:

```json
{"repository_url":"https://github.com/your-org/your-app","discover":true}
```

The browser runs inside the application's sandbox as a separate non-root user (UID 10002),
using TestQ-owned tooling. It does not need repository Playwright dependencies,
external browser services, a host application port, or Ollama.

Defaults in `.env.example`: `MAX_PAGES=12`, `MAX_DEPTH=3`, `NAVIGATION_TIMEOUT=8`,
`ACTION_TIMEOUT=3`, `DISCOVERY_TIMEOUT=60`, `DISCOVERY_TRACE_ENABLED=true`.
Timeout values are seconds. The whole-run deadline also applies during discovery.

Discovery records actual page status, title, same-origin links, buttons, inputs,
forms, selector candidates, request metadata, console messages and browser errors.
404 pages are recorded as HTTP errors and do not stop safe exploration of other
links. The map is available through `/api/test-runs/{id}/discovery`; artifacts and
verified download links through `/api/test-runs/{id}/evidence`.

Artifacts live under `evidence/<run_id>/discovery/<session_id>/`: viewport screenshots,
sanitized action traces, console/network/browser-error JSON, the application map,
and application-log references. They are exported and hash-verified before cleanup.
Limits include 8 MiB per artifact and 64 MiB per session by default.

## Deterministic test engine (Phase 3)

To execute deterministic tests following application discovery, set `testing_enabled: true`:

```json
{
  "repository_url": "https://github.com/your-org/your-app",
  "discover": true,
  "testing_enabled": true
}
```

> **Note:** `testing_enabled: true` requires `discover: true` because test cases are
> deterministically derived from the discovered application map. Setting `testing_enabled: true`
> with `discover: false` is rejected immediately with HTTP 400.

### Pipeline and execution

```text
READY → DISCOVERING → TESTING → COMPLETED
```

1. **Baseline Test Generation:** `BaselineTestGenerator` inspects the persisted `ApplicationMap`
   and produces structured test cases without any AI:
   - `HOME-001`: Root page smoke test (page load, URL match, element presence).
   - `NAV-xxx`: Navigation tests checking discovered same-origin links.
   - `UI-xxx`: Form interaction tests exercising discovered buttons, inputs, and controls.
   - `API-xxx`: API tests verifying discovered endpoints against loopback.
2. **In-Sandbox Runners:**
   - UI tests run via `testq_browser.test_runner` using Playwright in the sandbox as UID 10002.
   - API tests run via `testq_browser.api_runner` using HTTPX in the sandbox against `127.0.0.1:<port>`.
   - Single-element selector resolution (`locator.count() == 1`) ensures safe, unambiguous interactions.
3. **Execution Controls & Limits:**
   - `MAX_TESTS_PER_RUN=50`: Caps total tests executed per run.
   - `MAX_STEPS_PER_TEST=20`: Caps actions/assertions per test.
   - `TEST_ACTION_TIMEOUT=5`: Timeout per individual action (seconds).
   - `TEST_TIMEOUT=30`: Timeout per complete test case (seconds).
4. **Outcomes & Evidence:**
   - Outcomes: `PASS`, `FAIL`, `ERROR`, `TIMEOUT`, `CANCELLED`.
   - Evidence stored under `evidence/<run_id>/testing/<test_result_id>/` (viewport screenshots,
     execution logs, console logs, network events).
   - Endpoints: `GET /api/test-runs/{id}/test-cases` and `GET /api/test-runs/{id}/test-results`.

### Scope and Boundary Limits (Phase 3)

- **Baseline Tests:** Baseline tests (`HOME-001`, `NAV-xxx`, `UI-xxx`, `API-xxx`) are generated 100% deterministically from the application map.
- **NO AI Bug Classification:** Assertion failures and runtime errors are recorded as raw outcomes;
  no severity scores, confidence ratings, or automated bug reports are created.
- **Controlled Sandbox Environment:** Tests run in the existing isolated container with loopback
  networking only. No arbitrary code execution (`eval`, shell execution) is allowed.

## AI Test Generation (Phase 4)

Phase 4 introduces intelligent AI test planning and test generation using local **Ollama** (`qwen3:8b` by default).

### Key Architectural Guarantees

1. **Free MVP:** 100% local and free. No OpenAI, Gemini, Groq, or Anthropic API keys required.
2. **AI Reasons, Deterministic Code Executes:** The AI generates structured test definitions only (JSON/Pydantic).
   It has zero execution privileges (no shell, Python, JS eval, or Docker commands).
3. **Execution through Phase 3 Engine:** All AI-generated tests are executed by the hardened Phase 3 `TestExecutor`
   inside the sandbox via Playwright and HTTPX.
4. **Untrusted Observations vs. Instructions:** Repository contents, HTML, DOM text, console logs, and READMEs
   are treated strictly as observations. System instructions have higher authority, preventing prompt injection.
5. **Deterministic Deduplication:** AI tests are deduplicated against baseline tests and across other AI tests.
6. **Isolated Sandbox Boundary:** Untrusted code in the container cannot reach the host Ollama endpoint.
7. **Graceful Fallback:** If Ollama is offline or times out, an AI warning is recorded and deterministic baseline
   tests execute to completion. AI downtime is never reported as an application bug.
8. **Origin Distinguishability:** The `TestCase` model and API (`/api/test-runs/{id}/test-cases`) distinguish
   `source="baseline"` from `source="ai"`.

### Environment Configuration

```dotenv
AI_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
AI_MODEL=qwen3:8b
AI_ENABLED=true
AI_MAX_GENERATED_TESTS=20
AI_MAX_STRATEGY_ITEMS=15
AI_MAX_RETRIES=2
AI_REQUEST_TIMEOUT=45.0
AI_MAX_OUTPUT_BYTES=262144
```

## Hackathon Hardening (Phase 4.5)

Phase 4.5 completes the end-to-end hackathon loop with lightweight AI failure analysis,
a controlled demo application with intentional defects, and an interactive real-time dashboard.

### Complete Hackathon Workflow

```text
GitHub Repository (or Local Demo Store)
       ↓
Docker Sandbox (Non-root, loopback network isolation)
       ↓
Playwright Discovery (Pages, Forms, Inputs, Buttons, APIs)
       ↓
AI Test Strategy (15 QA Categories)
       ↓
AI Test Generation (Structured TestDefinitions)
       ↓
Deterministic Execution (In-Sandbox Playwright / HTTPX)
       ↓
Intentional Bug Detection (e.g., broken cart checkout link, invalid quantity 0)
       ↓
AI Failure Analysis (Structured FailureAnalysis: title, severity, category, root cause, reproduction)
       ↓
SQLite Persistence (TestCases, TestResults, FailureAnalyses, Evidence)
       ↓
Interactive Real-Time Dashboard (/dashboard)
       ↓
Container & Workspace Cleanup (0 orphaned containers)
```

### Key Capabilities

1. **Lightweight AI Failure Analysis:**
   - Evaluates `FAIL`, `ERROR`, and `TIMEOUT` results using structured AI prompts.
   - Outputs schema-validated `FailureAnalysis` (`title`, `severity`, `category`, `summary`, `likely_root_cause`, `reproduction_steps`, `evidence_references`, `confidence`).
   - Treats all application observations as untrusted data.
   - Non-crashing: If Ollama is offline or times out, the test result remains recorded, a warning is logged, and the run finishes successfully.
   - Endpoints: `GET /api/test-runs/{id}/failures` and `GET /api/test-runs/{id}/failures/{failure_id}`.

2. **Controlled Demo Application (`demo/`):**
   - Standalone Node.js Express e-commerce application with pages (`/`, `/products`, `/login`, `/cart`, `/checkout`) and APIs.
   - Includes 3 repeatable, deterministic bugs:
     - `BUG-001`: Checkout accepts quantity 0.
     - `BUG-002`: Login accepts invalid email format.
     - `BUG-003`: Cart proceeds to broken navigation route `/checkout-broken` (404).

3. **Interactive Real-Time Dashboard:**
   - Pre-rendered, zero-config dashboard served directly by FastAPI at `http://localhost:8000/dashboard`.
   - Distinguishes baseline tests from AI tests with origin badges.
   - Prominently displays actionable AI Bug Finding cards with severity indicators, reproduction steps, root cause analysis, and confidence scores.

### Scope Boundary Notice

Full Phase 5 (Runtime monitoring, static analysis) and full Phase 6 (advanced bug deduplication, automated source code repair) are NOT enabled. Development is stopped after Phase 4.5.



## Modern Web UI & Interactive Dashboard

The interactive UI lives in `frontend/` and is built with React 18, TypeScript, TailwindCSS, Motion, Radix UI, Three.js, and Vite.

With the backend running on port 8000, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** to access the dashboard.
- **Welcome Page**: Interactive 3D sculpture and quick-start actions.
- **Runs Overview**: Live status cards, historical runs, and filtering.
- **Run Details**: Real-time pipeline progress, terminal logs, application map discovery hierarchy, test cases, and captured screenshot/log evidence.
- **Failure Analysis**: Confirmed bug reports with automated root cause identification, reproduction steps, and severity badges.
