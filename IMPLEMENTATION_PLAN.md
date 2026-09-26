# TestQ — Implementation Plan

> **Independent AI QA Agent**
> *"Let AI build it. Let independent AI try to break it."*

---

## Original Phase 0 Workspace Audit (historical)

### Original State: **Empty Workspace**

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

At the Phase 0 audit, the workspace was empty apart from the specification documents. This historical baseline has been superseded by the verified Phase 1 implementation below.

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
| AI provider           | Ollama (local default)         | Most accessible; behind provider abstraction         |
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

### Phase 1 — Execution Foundation — Hardened and verified

Verified 2026-09-24. This historical Phase 1 result is preserved; Phase 2 verification is recorded below.

| Implemented task | Verification |
| --- | --- |
| FastAPI, async SQLite, project/run/log schemas and APIs | Existing regression coverage retained |
| Git clone and default-branch resolution | Real local Git fixtures with default branch trunk |
| Root/custom-port/nested standalone app detection | Detector tests; real custom-port Node startup |
| Non-root Node and Python images | Images rebuilt; real Node and FastAPI pipelines pass |
| Install/build/start/health orchestration | Real success, install failure, build failure, startup failure |
| Container ownership before create; nested cleanup | Copy failure, install/build/startup failure, unexpected exception, success |
| Command timeout kills execution | Real sleeping command and long-running build terminated |
| Whole-run monotonic deadline | Real active build terminated on deadline |
| Cancellation request, signal, final state | Real cancel endpoint stops work and removes sandbox |
| Enforced transitions and reliable JSON progress | Invalid-transition, cancellation-race and reload assertions |
| Retained stdout/stderr | Application and command logs retrieved after cleanup |
| Stable root-based paths and async SQLite URL | Different-cwd settings and additive migration tests |
| Development dependencies at build; production runtime | Real dev-only build helper and runtime environment assertion |
| Runtime networking restrictions | Loopback health passes; public-IP request fails after disconnect |
| Restart recovery | Label-scoped adoption/cleanup and terminal-state regression |

### Phase 1 final gate

- [x] Container cleanup on normal success and every tested failure path.
- [x] Command timeouts terminate execution and preserve available logs.
- [x] Whole-run deadline exists and stops active work.
- [x] Cancellation signals the worker and stops active Docker execution.
- [x] Invalid state transitions are rejected.
- [x] Progress changes persist to SQLite.
- [x] Application stdout/stderr is retained and retrievable.
- [x] Async SQLite configuration is consistent.
- [x] Runtime paths are independent of cwd.
- [x] Node build dependencies are available; runtime uses production settings.
- [x] Networking reviewed: setup enabled; runtime disconnected except loopback.
- [x] Both sandbox images use a non-root application user.
- [x] Resource and privilege restrictions remain intact and are tested.
- [x] Original 57-test coverage retained; default-branch assertion updated for remote HEAD.
- [x] New regression tests pass.
- [x] Successful Node and FastAPI integration pipelines pass.
- [x] Install/build/startup failure integration pipelines pass.
- [x] API cancellation integration passes.
- [x] Tests verify their containers and clone workspaces are removed.

Verification commands (backend directory):

```powershell
$env:TESTQ_DOCKER_TESTS = '1'
python -m pytest tests -q -p no:cacheprovider
python tests/test_integration_local.py
```

Result: **87 passed**, including **10 real Docker cases**, with three existing
Pydantic-schema pytest collection warnings. The original Express integration also
passed. Git-to-Docker integration uses local Git fixtures rather than an external
GitHub repository; URL-validation/API coverage is separate. Docker integration is
opt-in for ordinary test runs.

### Remaining Phase 1 limitations

- Supported deployment is one backend process/instance; cancellation signals are
  in memory, with a persisted request flag and startup recovery, not a durable queue.
- Setup/build networking is unrestricted bridge access for dependencies/assets;
  package scripts share that access. Runtime is loopback-only. External runtime
  APIs/databases, shared monorepo workspaces and multiple services are unsupported.
- Immediate removal cannot be guaranteed while Docker/host is unavailable. Cleanup
  retries and reports errors; the lifetime watchdog bounds execution but does not
  remove stopped containers. Unlabelled old containers require manual review.
- Stdout/stderr are bounded and exported at teardown, not streamed live. An abrupt
  backend/host crash may lose unexported output. Logs are not tamper-proof evidence.
- Database migration is the tested additive Phase 1 change, not a general migration
  framework. Existing databases in other directories must be explicitly configured.
- Sandbox images are prebuilt and checked by version label; provisioning is outside
  the per-run deadline. No automatic preservation/debug mode is enabled.
- READY means health was verified and Phase 1 resources cleaned, not a hosted preview.

At the Phase 1 milestone, no browser tooling or AI tests had been added. Phase 2 now adds deterministic browser discovery only.

---

### Phase 2 — Application Discovery — Verified 2026-09-25

**Goal achieved:** the live READY application is inspected with controlled same-container
Playwright, producing a persisted map and retained evidence before sandbox cleanup.
DISCOVERY_COMPLETE means discovery only; no tests are generated and no observations
are classified as bugs.

| Task | Verification | Status |
| --- | --- | --- |
| Playwright/Chromium in both TestQ images | Both images built; real sandboxed non-root Chromium launches pass | Complete |
| Live pipeline integration | READY → DISCOVERING → DISCOVERY_COMPLETE before final cleanup | Complete |
| Homepage and same-origin BFS | Real four-page fixture; normalized/deduplicated URLs; external requests blocked | Complete |
| Page/depth/navigation/session limits | Unit tests and real Docker limit/timeout cases | Complete |
| UI metadata and selectors | Buttons, login forms, inputs, select, checkbox, radio, textarea and ordered candidates | Complete |
| Network/console/browser observations | GET /api/products, deliberate console/page errors, failed external requests | Complete |
| Typed application map and SQLite | Session JSON, contextual evidence metadata, additive migration, API retrieval | Complete |
| Screenshots and sanitized traces | Actual exported PNGs visually inspected; ZIP action events inspected | Complete |
| Evidence export before cleanup | SHA-256/size/type checks, persisted map/log references, post-cleanup file assertions | Complete |
| Failure and cancellation | Broken 404, navigation timeout, discovery timeout, launch failure, API cancellation | Complete |
| Sandbox restrictions | No host mounts/socket/ports, non-root users, dropped capabilities, resource/network limits | Complete |
| Phase 1 regression | All original 87 tests pass, including 10 real Docker cases | Complete |
| Public supported application | Heroku Express sample, commit recorded below, discovery and cleanup verified | Complete |
| Documentation | README, architecture, environment example, this plan | Complete |

Final complete suite: **125 passed, 0 skipped, 3 existing collection warnings** in
113.95 seconds. This includes **20 real Docker tests** (10 original and 10 Phase 2)
and 28 new non-Docker tests. Command, from `backend`, with Docker running:

```powershell
$env:TESTQ_DOCKER_TESTS = '1'
$env:TESTQ_PUBLIC_APP_TEST = '1'
python -m pytest -q --tb=short
```

Retained manual-inspection evidence:

- Fixture run `61997881-ee90-41ef-a9da-c65b262c253c`: four pages, homepage/forms,
  `/second`, `/login`, and `/broken` (404, `http_error`); GET `/api/products` (200).
  Thirteen artifacts in `evidence/phase2-fixture/`, including four screenshots,
  four sanitized traces, console/network/errors, map and application logs.
- Public repository `https://github.com/heroku/node-js-getting-started`, commit
  `7233acafd6e9aa0a8cce2cd05188d0ae8f03ee8f`; final run
  `b0daca5c-fd1e-4f1b-9e0d-937d830153d2`, one homepage (200), seven retained artifacts
  in `evidence/phase2-verification/`. External CDN assets were blocked, visibly
  reducing styling. The sample executed on the existing Node 20 image despite its
  newer declared engine range; this is observed compatibility, not general support
  for newer Node APIs. No Phase 1 image runtime upgrade was made.

Scope limits are documented in ARCHITECTURE.md: anonymous path-based discovery,
no query/hash route exploration or click/form execution, blocked external services,
short observation window, privacy-reduced traces, and potential loss of unexported
in-flight evidence on an abrupt backend/daemon crash. Selectors are candidates,
not promises of uniqueness. Arbitrary visible secrets cannot be perfectly redacted.
These limits do not change the deterministic discovery milestone into QA completion.

**Stopped after Phase 2. Phase 3/AI generation/classification/reporting are not started.**

---
### Phase 3 — Deterministic Test Engine — Verified 2026-09-25

**Goal achieved:** Application Map → Deterministic Test Definitions → Schema Validation → Controlled Test Executor → In-Sandbox Playwright / HTTPX → Assertions → PASS/FAIL/ERROR/TIMEOUT/CANCELLED → Evidence → SQLite.
Strictly deterministic: NO AI test generation, NO bug classification, NO automatic bug reports.

| Task | Verification | Status |
| --- | --- | --- |
| Define test case & result JSON schemas | `backend/testq_browser/test_schemas.py` & `backend/app/schemas/test_case.py`; strict Pydantic models; unit tests in `test_phase3_schemas.py` | Complete |
| Database models & migrations | `TestCase` and `TestResult` ORM models in `backend/app/models/test_case.py`; additive migration for `testing_enabled` in `test_runs` and `test_result_id` in `evidence` | Complete |
| In-sandbox Playwright test runner | `backend/testq_browser/test_runner.py` running as UID 10002 inside sandbox; handles actions (`goto`, `click`, `fill`, etc.) and assertions (`page_loaded`, `url_matches`, `element_visible`, etc.) with selector resolution; unit tested in `test_selector_resolution.py` | Complete |
| In-sandbox HTTPX API test runner | `backend/testq_browser/api_runner.py` running as UID 10002 inside sandbox; tests loopback endpoints with assertions (`status_code`, `response_time`, `content_type`, `json_field_present`, `json_value`); unit tested in `test_api_runner.py` | Complete |
| Baseline deterministic test generator | `backend/app/services/baseline_generator.py` converting `ApplicationMap` into `HOME-001`, `NAV-xxx`, `UI-xxx`, and `API-xxx` test cases without AI; unit tested in `test_baseline_generator.py` | Complete |
| Controlled host Test Executor | `backend/app/services/test_executor.py` dispatching UI/API tests, enforcing test count limits (`MAX_TESTS_PER_RUN=50`), step limits (`MAX_STEPS_PER_TEST=20`), action timeouts (`TEST_ACTION_TIMEOUT=5s`), and test timeouts (`TEST_TIMEOUT=30s`); unit tested in `test_test_executor.py` | Complete |
| Host Playwright & API runners | `backend/app/services/playwright_runner.py` and `backend/app/services/api_tester.py` executing inside sandbox via `SandboxManager.execute` and extracting evidence | Complete |
| Evidence capture per test | `EvidenceManager` supporting `evidence/{run_id}/testing/{test_result_id}/` for screenshots, execution JSON, console, and network logs with SHA-256 verification | Complete |
| Live pipeline integration & state machine | `READY → DISCOVERING → TESTING → COMPLETED` (or `READY → DISCOVERING → DISCOVERY_COMPLETE` if testing disabled). Strict rejection of `testing_enabled: true` without `discover: true`; tested in `test_phase3_pipeline.py` | Complete |
| REST API endpoints | `GET /api/test-runs/{id}/test-cases`, `GET /api/test-runs/{id}/test-results`, and filtered evidence queries in `test_cases.py` and `discovery.py`; tested in `test_api.py` | Complete |
| Sandbox Docker images rebuilt | Rebuilt `testq-sandbox-node:latest` and `testq-sandbox-python:latest` with Playwright, HTTPX, and `testq_browser` | Complete |
| Real Docker pipeline & cancellation verification | `backend/tests/test_docker_deterministic_engine.py` testing live pipeline execution and mid-run cancellation with real Docker containers | Complete |
| Phase 1 & Phase 2 regression | All 125 existing tests pass cleanly; 0 pytest collection warnings | Complete |

### Phase 3 Verification Results

Full test suite execution (backend directory, Docker running):

```powershell
$env:TESTQ_DOCKER_TESTS = '1'
$env:TESTQ_PUBLIC_APP_TEST = '1'
pytest tests/ -q --tb=short
python tests/test_integration_local.py
```

Result: **197 passed, 0 failed, 0 warnings** in 132.91 seconds.
Includes:
- **23 real Docker tests**:
  - 10 Phase 1 hardening and isolation cases
  - 10 Phase 2 discovery cases (including public Heroku Express application)
  - 3 Phase 3 deterministic engine cases (`test_real_deterministic_testing_pipeline`, `test_real_deterministic_testing_active_cancellation`, `test_real_deterministic_testing_timeout`)
- **72 Phase 3-specific tests**:
  - `test_phase3_schemas.py` (15 tests)
  - `test_selector_resolution.py` (5 tests)
  - `test_api_runner.py` (16 tests, including response_time PASS/FAIL and path boundary protections)
  - `test_baseline_generator.py` (3 tests)
  - `test_test_executor.py` (5 tests, including MAX_TESTS_PER_RUN=50 truncation and action timeout)
  - `test_ui_actions.py` (6 tests: goto, click, fill, select, check, uncheck, wait)
  - `test_ui_assertions.py` (13 tests: all 7 assertions for PASS and FAIL)
  - `test_phase3_pipeline.py` (4 tests)
  - `test_docker_deterministic_engine.py` (3 real Docker tests)
  - `test_api.py` (2 configuration boundary tests: HTTP 400 rejection and HTTP 201 acceptance)

### Scope and Boundary Protections

- **No AI / LLM Integration:** Baseline test cases are derived strictly and deterministically from discovered routes, elements, and endpoints. Ollama/OpenAI is NOT called.
- **No Bug Classification or Reporting:** Test outcomes are recorded as structured execution results (`PASS`, `FAIL`, `ERROR`, `TIMEOUT`, `CANCELLED`). No severity, confidence scores, bug deduplication, or AI-written bug reports exist in this phase.
- **Strict Sandbox Constraints:** Test runner processes execute within the unprivileged container under UID 10002 with dropped Linux capabilities and isolated loopback networking.

### Phase 4 — AI Test Generation — Verified 2026-09-25

**Goal achieved:** Application Map + Project Manifest → AI Test Planner → Risk/Test Strategy → AI Test Generator → Strict Pydantic Validation & Deduplication → Phase 3 Deterministic Test Executor → In-Sandbox Playwright / HTTPX → Evidence + Test Results.
Free MVP: Uses local Ollama (`qwen3:8b` default). AI reasons; deterministic code executes. Untrusted observations strictly isolated from instructions.

| Task | Verification | Status |
| --- | --- | --- |
| Implement AI Provider abstraction | `backend/app/ai/base.py`; `AIProvider` ABC with timeout, structured response validation, and structured error taxonomy (`AIUnavailableError`, `AITimeoutError`, `AIInvalidOutputError`, etc.) | Complete |
| Implement Ollama Provider (Free V1) | `backend/app/ai/ollama.py`; connects to local Ollama (`/api/generate`), strips code fences, enforces response limits, maps network errors | Complete |
| Implement Test Planner (strategy generation) | `backend/app/services/test_planner.py`; generates structured `TestStrategy` from application map and manifest; enforces QA matrix categories, drops external URLs, treats observations as untrusted | Complete |
| Implement Test Generator (structured tests) | `backend/app/services/test_generator.py`; generates `AI-UI-xxx` and `AI-API-xxx` test cases; validates via Phase 3 `validate_test_definition`; enforces whitelisted actions and assertions | Complete |
| QA matrix categories & prompts | `backend/app/schemas/ai_test.py`; 15 QA matrix categories (`navigation`, `authentication`, `forms`, `validation`, `inputs`, `buttons`, `api`, `error handling`, `boundary values`, etc.) | Complete |
| Schema validation & deduplication | Strict Pydantic parsing, granular `validate_test_definition`, deterministic deduplication against baseline tests and among AI tests | Complete |
| Bounded retries and limits | `AI_MAX_GENERATED_TESTS=20`, `AI_MAX_STRATEGY_ITEMS=15`, `AI_MAX_RETRIES=2`, `AI_REQUEST_TIMEOUT=45.0`, `AI_MAX_OUTPUT_BYTES=262144` | Complete |
| Live pipeline integration | `backend/app/worker/pipeline.py`; synthesizes AI strategy and tests, combines with baseline tests, persists `source="baseline"` and `source="ai"`; graceful fallback on AI error | Complete |
| Unit and integration test suite | `test_ai_provider.py` (12 tests), `test_test_planner.py` (6 tests), `test_test_generator.py` (7 tests), `test_phase4_pipeline.py` (2 tests), `test_docker_ai_generation.py` (2 tests) | Complete |

### Phase 4 Verification Results

Full test suite execution (backend directory, Docker running):

```powershell
$env:TESTQ_DOCKER_TESTS = '1'
$env:TESTQ_PUBLIC_APP_TEST = '1'
pytest tests/ -q --tb=short
python tests/test_integration_local.py
```

Result: **225 passed, 1 skipped, 0 warnings** in 155.04 seconds.
Includes:
- **24 real Docker tests**:
  - 10 Phase 1 hardening and isolation cases
  - 10 Phase 2 discovery cases (including public Heroku Express application)
  - 3 Phase 3 deterministic engine cases
  - 1 Phase 4 real Docker AI generation pipeline case (`test_real_docker_ai_generated_test_execution`)
- **28 Phase 4-specific tests**:
  - `test_ai_provider.py` (12 tests)
  - `test_test_planner.py` (6 tests)
  - `test_test_generator.py` (7 tests)
  - `test_phase4_pipeline.py` (2 tests)
  - `test_docker_ai_generation.py` (1 passed, 1 skipped when local Ollama offline)
- **197 Phase 1–3 regression tests**: All pass cleanly with zero regressions.

---

### Phase 4.5 — Hackathon Hardening — Verified 2026-09-25

**Goal achieved:** Complete, reliable end-to-end hackathon demonstration:
Git Repo → Docker Sandbox → Discovery → AI Test Strategy → AI Test Generation → Deterministic Test Execution → Intentional Bug Detection → AI Failure Analysis → SQLite Persistence → Real-Time Dashboard → Resource Cleanup.

| Task | Verification | Status |
| --- | --- | --- |
| Implement AI Failure Analyzer | `backend/app/services/failure_analyzer.py`; structured failure diagnostics with severity, category, root cause, reproduction; unit tested in `test_failure_analyzer.py` | Complete |
| Database model & persistence | `FailureAnalysisRecord` in `backend/app/models/failure_analysis.py` with foreign keys to `TestResult` and `TestCase` | Complete |
| Failure Analysis API endpoints | `GET /api/test-runs/{id}/failures` and `GET /api/test-runs/{id}/failures/{failure_id}` in `backend/app/api/test_cases.py` | Complete |
| Pipeline integration | `backend/app/worker/pipeline.py`; automatically evaluates failed tests, persists `FailureAnalysisRecord`, gracefully continues if AI unavailable | Complete |
| Controlled Demo Application | `demo/` standalone Node.js Express store with 3 intentional bugs (`BUG-001` quantity 0, `BUG-002` invalid email, `BUG-003` broken cart navigation) | Complete |
| Real Docker end-to-end demo test | `backend/tests/test_demo_e2e.py`; executes full loop against demo store in real Docker sandbox, detects broken navigation, verifies failure analysis persistence and cleanup | Complete |
| Real-time Interactive Dashboard | `backend/app/static/dashboard.html` served at `http://localhost:8000/dashboard` and Next.js frontend in `frontend/` | Complete |

### Phase 4.5 Verification Results

Full test suite execution (backend directory, Docker running):

```powershell
$env:TESTQ_DOCKER_TESTS = '1'
$env:TESTQ_PUBLIC_APP_TEST = '1'
pytest tests/ -q --tb=short
python tests/test_integration_local.py
```

Result: **238 passed, 1 skipped, 0 warnings** in 182.15 seconds.
Includes:
- **25 real Docker tests**:
  - 10 Phase 1 hardening and isolation cases
  - 10 Phase 2 discovery cases (including public Heroku Express application)
  - 3 Phase 3 deterministic engine cases
  - 1 Phase 4 real Docker AI generation pipeline case
  - 1 Phase 4.5 real Docker demo store end-to-end case (`test_demo_store_e2e_pipeline`)
- **40 AI & Failure Analysis tests**:
  - `test_ai_provider.py` (12 tests)
  - `test_test_planner.py` (6 tests)
  - `test_test_generator.py` (7 tests)
  - `test_failure_analyzer.py` (11 tests)
  - `test_phase4_pipeline.py` (2 tests)
  - `test_docker_ai_generation.py` (1 passed, 1 skipped when local Ollama offline)
  - `test_demo_e2e.py` (1 passed in real Docker)
- **198 Phase 1–3 regression tests**: All pass cleanly with zero regressions.

**Stopped after Phase 4.5. Phase 5 (Runtime Monitoring + Static Analysis) and Phase 6 (AI Failure Analysis) are not started.**

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

**Phase 4.5 Hackathon Hardening verified. Complete end-to-end hackathon demonstration ready. Stopped before Phase 5 (Runtime Monitoring + Static Analysis) and full Phase 6 (Advanced Bug Deduplication / Autonomous Fixing).**

---

## MVP Definition of Done Checklist

| #  | Criterion                                          | Status |
| -- | -------------------------------------------------- | ------ |
| 1  | User submits a GitHub repository through the API   | ✅     |
| 2  | TestQ clones it                                    | ✅     |
| 3  | TestQ detects the supported stack                  | ✅     |
| 4  | TestQ creates an isolated sandbox                  | ✅     |
| 5  | TestQ installs dependencies                        | ✅     |
| 6  | TestQ builds the application                       | ✅     |
| 7  | TestQ starts the application                       | ✅     |
| 8  | TestQ verifies the application is running          | ✅     |
| 9  | TestQ discovers application functionality          | Complete |
| 10 | TestQ generates meaningful tests                   | Complete |
| 11 | TestQ executes UI/API tests                        | Complete |
| 12 | TestQ captures real evidence                       | Complete |
| 13 | TestQ monitors runtime failures                    | ⬜     |
| 14 | TestQ analyzes failures with AI                    | Complete |
| 15 | TestQ distinguishes bug/test/environment failures  | ⬜     |
| 16 | TestQ reproduces important failures                | ⬜     |
| 17 | TestQ deduplicates related failures                | ⬜     |
| 18 | TestQ generates a professional QA report           | ⬜     |
| 19 | Dashboard displays actual results                  | Complete |
| 20 | Demo repository reliably demonstrates full flow    | Complete |

---

*Last updated: 2026-09-25. Phase 4.5 verified; stopped for the next instruction.*


Final cleanup check: `docker ps -a --filter label=testq.managed=true` returned no
containers. Sanitized trace ZIP structure and event data were inspected; the
Playwright trace viewer UI itself was not separately exercised.

