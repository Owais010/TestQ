# TestQ — Implementation Plan

> **Independent AI QA Agent**
> *"Let AI build it. Let independent AI try to break it."*

---

## Workspace Audit Summary

### Current State: **Empty Workspace**

| Aspect              | Status                                                    |
| ------------------- | --------------------------------------------------------- |
| Workspace path      | `c:\Users\owais\OneDrive\Documents\TestQ`                 |
| Git repository      | ❌ Not initialized                                        |
| Existing code       | ❌ None — only spec documents present                     |
| Frontend            | ❌ Not started                                            |
| Backend             | ❌ Not started                                            |
| Docker/Sandbox      | ❌ Not started                                            |
| Demo app            | ❌ Not started                                            |
| Tests               | ❌ Not started                                            |
| Documentation       | ✅ ARCHITECTURE.md created                                |

### Available Tools on Host

| Tool     | Version                    |
| -------- | -------------------------- |
| Python   | 3.13.15                    |
| Node.js  | v26.7.0                    |
| npm      | 11.19.0                    |
| Docker   | 29.7.2                     |
| Git      | 2.55.0                     |

### Files Present

```
TestQ/
├── TestQ_Project_Document.docx        # Product spec (read ✓)
├── TestQ_How_To_Build_and_Solve.docx  # Build blueprint (read ✓)
└── ARCHITECTURE.md                    # Architecture doc (created ✓)
```

### Conclusion

The workspace is **completely empty** — no code, no configs, no Git history. We are starting from scratch with clear specification documents. This is a greenfield implementation.

---

## Technology Decisions

| Decision              | Choice                  | Rationale                                            |
| --------------------- | ----------------------- | ---------------------------------------------------- |
| Frontend framework    | Next.js 15 (App Router) | Spec requirement; SSR, routing, modern React          |
| Frontend language     | TypeScript               | Spec requirement; type safety                        |
| Frontend styling      | Tailwind CSS 4           | Spec requirement; rapid UI development               |
| Backend framework     | FastAPI                  | Spec requirement; async, Pydantic, Python            |
| Database              | SQLite + SQLAlchemy      | Spec requirement; easy migration to PostgreSQL       |
| Sandbox               | Docker SDK for Python    | Spec requirement; disposable containers              |
| Browser testing       | Playwright (Python)      | Spec requirement; browser automation                 |
| API testing           | HTTPX                    | Async HTTP client; pairs with FastAPI                |
| AI provider           | OpenAI (initial)         | Most accessible; behind provider abstraction         |
| Worker architecture   | asyncio background tasks | Simple first; upgrade to Redis/Celery later          |
| Package manager (FE)  | npm                      | Standard; compatible with deployment                 |
| Package manager (BE)  | pip + venv               | Simple; pyproject.toml for metadata                  |

---

## Proposed Directory Structure

```
TestQ/
│
├── frontend/                        # Next.js 15 application
│   ├── app/                         # App Router pages
│   │   ├── layout.tsx
│   │   ├── page.tsx                 # Landing / repo input
│   │   ├── runs/
│   │   │   ├── [id]/
│   │   │   │   ├── page.tsx         # Test run dashboard
│   │   │   │   ├── bugs/page.tsx
│   │   │   │   ├── tests/page.tsx
│   │   │   │   ├── evidence/page.tsx
│   │   │   │   └── logs/page.tsx
│   │   │   └── page.tsx             # Run list
│   │   └── globals.css
│   ├── components/
│   │   ├── ui/                      # Base UI components
│   │   ├── dashboard/               # Dashboard-specific
│   │   └── layout/                  # Layout components
│   ├── lib/
│   │   ├── api.ts                   # API client
│   │   ├── types.ts                 # TypeScript types
│   │   └── utils.ts
│   ├── public/
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.ts
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app
│   │   ├── config.py                # Settings
│   │   ├── database.py              # DB engine + session
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── test_runs.py
│   │   │   └── evidence.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── project.py
│   │   │   ├── test_run.py
│   │   │   ├── test_case.py
│   │   │   ├── test_result.py
│   │   │   ├── bug.py
│   │   │   ├── evidence.py
│   │   │   └── log.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── test_run.py
│   │   │   ├── test_case.py
│   │   │   ├── bug.py
│   │   │   └── evidence.py
│   │   ├── services/
│   │   │   ├── __init__.py
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
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── openai_provider.py
│   │   │   └── prompts/
│   │   │       ├── analyzer.py
│   │   │       ├── test_generator.py
│   │   │       └── classifier.py
│   │   └── worker/
│   │       ├── __init__.py
│   │       ├── orchestrator.py
│   │       └── pipeline.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_project_detector.py
│   │   ├── test_schemas.py
│   │   ├── test_sandbox.py
│   │   ├── test_api.py
│   │   └── conftest.py
│   ├── requirements.txt
│   └── pyproject.toml
│
├── sandbox/
│   ├── Dockerfile.node
│   ├── Dockerfile.python
│   └── scripts/
│       └── entrypoint.sh
│
├── demo/
│   └── vulnerable-app/
│       ├── package.json
│       ├── next.config.js
│       ├── src/
│       │   ├── app/
│       │   ├── pages/api/
│       │   └── components/
│       └── README.md
│
├── docs/
│   └── API.md
│
├── docker-compose.yml
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── .env.example
└── .gitignore
```

---

## Phase-by-Phase Implementation Plan

### Phase 0 — Workspace Audit and Architecture ✅ COMPLETE

| Task                              | Status |
| --------------------------------- | ------ |
| Read specification documents      | ✅     |
| Inspect workspace                 | ✅     |
| Check available dev tools         | ✅     |
| Create ARCHITECTURE.md            | ✅     |
| Create IMPLEMENTATION_PLAN.md     | ✅     |

---

### Phase 1 — Execution Foundation

**Goal:** GitHub URL → Clone → Detect → Docker Sandbox → Build → Start → Health Check → Real Status

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Initialize Git repository                      | ⬜     | P0       |
| Create .gitignore, .env.example                | ⬜     | P0       |
| Set up backend project (FastAPI + deps)        | ⬜     | P0       |
| Define Pydantic schemas for all entities       | ⬜     | P0       |
| Define SQLAlchemy models                       | ⬜     | P0       |
| Set up SQLite database + migrations            | ⬜     | P0       |
| Implement GitHub Service (clone, branch)       | ⬜     | P0       |
| Implement Project Detector (Next.js, React/Vite, Node, FastAPI) | ⬜ | P0 |
| Implement Sandbox Manager (Docker SDK)         | ⬜     | P0       |
| Create sandbox Dockerfiles (Node, Python)      | ⬜     | P0       |
| Implement Build Manager (install, build, start)| ⬜     | P0       |
| Implement Port Detector                        | ⬜     | P0       |
| Implement Health Checker                       | ⬜     | P0       |
| Implement Application Runner (orchestrates build pipeline) | ⬜ | P0 |
| Implement Worker Orchestrator (background tasks) | ⬜   | P0       |
| Create API routes: POST /api/test-runs, GET /api/test-runs/{id} | ⬜ | P0 |
| Create API routes: POST /api/projects, GET /api/projects/{id} | ⬜ | P0 |
| Write unit tests for Project Detector          | ⬜     | P0       |
| Write unit tests for schemas                   | ⬜     | P0       |
| Integration test: clone → detect → build → health check | ⬜ | P0 |
| Structured logging setup                       | ⬜     | P1       |

**Success Criteria:**
- A real Next.js/React/FastAPI app can be cloned from GitHub
- Framework, package manager, and commands are correctly detected
- App builds and starts in an isolated Docker container
- Health check confirms the app is running
- Build failures are reported honestly with logs preserved
- API returns real status for each state transition

---

### Phase 2 — Application Discovery

**Goal:** Playwright explores the running app → routes, forms, buttons, APIs discovered → application map generated

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Install Playwright in sandbox environment      | ⬜     | P0       |
| Implement Discovery Service                    | ⬜     | P0       |
| Crawl homepage + follow links                  | ⬜     | P0       |
| Discover forms, inputs, buttons                | ⬜     | P0       |
| Detect API calls from network interception     | ⬜     | P0       |
| Identify auth-related pages (login, register)  | ⬜     | P0       |
| Generate normalized application map JSON       | ⬜     | P0       |
| Implement Evidence Manager (screenshots, traces)| ⬜    | P0       |
| Combine repo analysis with browser discovery   | ⬜     | P1       |
| Write tests for discovery service              | ⬜     | P1       |

---

### Phase 3 — Deterministic Test Engine

**Goal:** Structured test definitions → Deterministic executor → Results with evidence

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Define test case JSON schema                   | ⬜     | P0       |
| Implement Test Executor (schema interpreter)   | ⬜     | P0       |
| Implement Playwright Runner (UI tests)         | ⬜     | P0       |
| Implement API Tester (HTTPX)                   | ⬜     | P0       |
| Implement baseline deterministic test suite    | ⬜     | P0       |
| Evidence capture per test (screenshot, console, network) | ⬜ | P0 |
| Test results stored in database                | ⬜     | P0       |
| API routes: GET /api/test-runs/{id}/tests      | ⬜     | P0       |
| API routes: GET /api/test-runs/{id}/evidence   | ⬜     | P0       |
| Write tests for executor                       | ⬜     | P1       |

---

### Phase 4 — AI Test Generation

**Goal:** AI receives project manifest + app map → generates structured test cases

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Implement AI Provider abstraction              | ⬜     | P0       |
| Implement OpenAI Provider                      | ⬜     | P0       |
| Implement Test Planner (strategy generation)   | ⬜     | P0       |
| Implement Test Generator (structured tests)    | ⬜     | P0       |
| QA matrix categories in prompts                | ⬜     | P0       |
| Schema validation on AI output                 | ⬜     | P0       |
| Write tests for test generation                | ⬜     | P1       |

---

### Phase 5 — Runtime Monitoring + Static Analysis

**Goal:** Monitor runtime during testing + run static analysis tools

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Implement Runtime Monitor (stdout, stderr, crashes) | ⬜ | P0      |
| Capture HTTP 500s, console errors, crashes     | ⬜     | P0       |
| Implement Static Analyzer (ESLint, Semgrep, npm audit) | ⬜ | P0 |
| Correlate runtime events with test cases       | ⬜     | P1       |
| Store findings as evidence (not automatic bugs)| ⬜     | P0       |
| API routes: GET /api/test-runs/{id}/logs       | ⬜     | P0       |

---

### Phase 6 — AI Failure Analysis + Classification

**Goal:** AI receives evidence → classifies failures → assigns severity/confidence

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Implement AI Failure Analyzer                  | ⬜     | P0       |
| Implement Bug Classifier                       | ⬜     | P0       |
| Structured JSON output with classification     | ⬜     | P0       |
| Severity + confidence assignment               | ⬜     | P0       |
| Separation of OBSERVED vs AI ANALYSIS          | ⬜     | P0       |
| API routes: GET /api/test-runs/{id}/bugs       | ⬜     | P0       |

---

### Phase 7 — Bug Reproduction + Deduplication

**Goal:** Replay tests → confirm failures → cluster related bugs

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Implement Reproduction Engine                  | ⬜     | P0       |
| Replay failed tests 2-3 times                  | ⬜     | P0       |
| Implement Bug Deduplicator                     | ⬜     | P0       |
| Cluster by endpoint, exception, error signature| ⬜     | P0       |
| "Seen in N tests" aggregation                  | ⬜     | P0       |

---

### Phase 8 — Dashboard Integration

**Goal:** Frontend displays real data from backend APIs

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Initialize Next.js project                     | ⬜     | P0       |
| Set up Tailwind CSS + dark theme               | ⬜     | P0       |
| Landing page (repo URL input, Start Testing)   | ⬜     | P0       |
| Real-time test run progress page               | ⬜     | P0       |
| Dashboard overview (QA score, summary)         | ⬜     | P0       |
| Bugs page (list, filter, detail)               | ⬜     | P0       |
| Test cases page                                | ⬜     | P0       |
| Evidence viewer (screenshots, traces)          | ⬜     | P0       |
| Logs viewer                                    | ⬜     | P0       |
| Project analysis page                          | ⬜     | P1       |
| Recommendations page                           | ⬜     | P1       |
| API client consuming real backend              | ⬜     | P0       |
| Responsive design                              | ⬜     | P1       |
| Polish animations and transitions              | ⬜     | P2       |

---

### Phase 9 — Demo Vulnerable Application

**Goal:** Predictable demo that reliably demonstrates the full pipeline

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| Create Next.js demo app with intentional bugs  | ⬜     | P0       |
| Inject: broken form validation                 | ⬜     | P0       |
| Inject: API 500 error                          | ⬜     | P0       |
| Inject: broken navigation / 404 route          | ⬜     | P0       |
| Inject: authentication/authorization flaw      | ⬜     | P0       |
| Inject: edge-case runtime crash                | ⬜     | P0       |
| Inject: console error                          | ⬜     | P0       |
| "Try Demo" button in frontend                  | ⬜     | P0       |
| Verify demo produces consistent findings       | ⬜     | P0       |

---

### Phase 10 — End-to-End Validation + Cleanup

**Goal:** Complete validation, documentation, cleanup

| Task                                           | Status | Priority |
| ---------------------------------------------- | ------ | -------- |
| End-to-end test: real GitHub repo → report     | ⬜     | P0       |
| End-to-end test: demo app → report             | ⬜     | P0       |
| Verify all 20 MVP success criteria             | ⬜     | P0       |
| docker-compose.yml for full stack              | ⬜     | P0       |
| README.md with setup instructions              | ⬜     | P0       |
| API documentation                              | ⬜     | P1       |
| Code cleanup and consistency review            | ⬜     | P1       |
| Security review of sandbox                     | ⬜     | P0       |
| Performance check                              | ⬜     | P2       |

---

## Risks and Mitigations

| Risk                                      | Likelihood | Impact   | Mitigation                                         |
| ----------------------------------------- | ---------- | -------- | -------------------------------------------------- |
| Docker-in-Docker complexity on Windows    | High       | High     | Use Docker SDK from host, not DinD                 |
| AI hallucinating test selectors           | Medium     | Medium   | Schema validation + fallback selectors             |
| Playwright flakiness in container         | Medium     | Medium   | Retries, timeouts, headless Chromium               |
| Build timeout for large repos             | Medium     | Low      | Configurable timeouts, fail honestly               |
| AI API rate limits                        | Low        | Medium   | Provider abstraction, caching, retry with backoff  |
| Sandbox escape                            | Low        | Critical | No privileged mode, no docker socket, limits       |
| OneDrive sync conflicts                   | Medium     | Low      | Use .gitignore to exclude large/temp files         |

---

## Security Considerations

1. **Never execute repo code on the host** — always in disposable Docker containers
2. **No Docker socket in sandbox** — prevents container escape
3. **No privileged containers** — `--security-opt=no-new-privileges`
4. **Resource limits** — CPU, memory, PID limits on every container
5. **Wall-clock timeout** — hard kill after max time
6. **No host mounts** — isolated filesystem only
7. **No secrets in sandbox** — API keys never injected into untrusted containers
8. **Input validation** — Pydantic schemas on all API inputs
9. **AI output validation** — JSON schema validation on all AI responses
10. **Automatic cleanup** — containers and volumes removed after every run
11. **Network restriction** — sandbox on isolated Docker network where possible
12. **Structured AI** — AI outputs JSON, never executes commands directly

---

## Current Phase

> **Phase 0 — Complete ✅**
>
> Ready to begin **Phase 1 — Execution Foundation**

---

## MVP Definition of Done Checklist

| #  | Criterion                                          | Status |
| -- | -------------------------------------------------- | ------ |
| 1  | User enters a GitHub repository                    | ⬜     |
| 2  | TestQ clones it                                    | ⬜     |
| 3  | TestQ detects the supported stack                  | ⬜     |
| 4  | TestQ creates an isolated sandbox                  | ⬜     |
| 5  | TestQ installs dependencies                        | ⬜     |
| 6  | TestQ builds the application                       | ⬜     |
| 7  | TestQ starts the application                       | ⬜     |
| 8  | TestQ verifies the application is running          | ⬜     |
| 9  | TestQ discovers application functionality          | ⬜     |
| 10 | TestQ generates meaningful tests                   | ⬜     |
| 11 | TestQ executes UI/API tests                        | ⬜     |
| 12 | TestQ captures real evidence                       | ⬜     |
| 13 | TestQ monitors runtime failures                    | ⬜     |
| 14 | TestQ analyzes failures with AI                    | ⬜     |
| 15 | TestQ distinguishes bug/test/environment failures  | ⬜     |
| 16 | TestQ reproduces important failures                | ⬜     |
| 17 | TestQ deduplicates related failures                | ⬜     |
| 18 | TestQ generates a professional QA report           | ⬜     |
| 19 | Dashboard displays actual results                  | ⬜     |
| 20 | Demo repository reliably demonstrates full flow    | ⬜     |

---

*Last updated: Phase 0 complete. Proceeding to Phase 1 upon approval.*
