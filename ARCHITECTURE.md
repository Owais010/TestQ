# TestQ — Architecture Document

> **Independent AI QA Agent**
> *"Let AI build it. Let independent AI try to break it."*

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
DATABASE_URL=sqlite:///./testq.db

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
