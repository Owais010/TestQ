# TestQ functionality and hackathon audit — 26 September 2026

**Verdict: the interface and execution infrastructure are credible, but the current configuration is not ready for a reliable live AI bug-finding demonstration.** The most important defect is a false pass on a known HTTP 404. The other immediate blocker is live AI generation: the configured model is missing, and an isolated attempt with the installed model timed out.

This is an executed audit of the current local checkout, not an assessment based on the README's earlier verification claims. Product source and `.env` were not changed. Docker Desktop and the backend were started for testing. The audit harness uses a separate database and artifact directory, preserving the existing workspace records.

**Measured verification**

| Check | Result | What it proves / limit |
|---|---|---|
| Production frontend build | PASS | TypeScript and Vite production build succeed |
| Frontend formatting | PASS | Prettier checks succeed |
| Chromium frontend suite with live backend | 15 passed, 35.2 seconds | Navigation, form contracts, cancellation contract, empty/error states, filters, preferences, responsive layout, keyboard behavior and selected Axe accessibility checks; one read-only live API/artifact test |
| Backend default suite | 214 passed, 26 skipped, 24.08 seconds | Unit/service/API coverage; optional integrations excluded |
| Backend with Docker and live Ollama enabled | 238 passed, 1 failed, 1 skipped, 173.46 seconds | Real sandbox/discovery/execution/cleanup tests pass; live planner/generator fails because configured model is absent; public-repository check was separately gated |
| Separately enabled public GitHub test | 1 passed, 10.28 seconds | `heroku/node-js-getting-started`: real GitHub clone, build, health, discovery, retained screenshot/trace and cleanup; discovery-only, not AI bug detection |
| Fresh local demo, current configuration | COMPLETED; 13 PASS, 0 AI tests, 0 findings | Real Node sandbox, discovery and deterministic execution; AI fell back after missing-model errors |
| Fresh local demo, process-only `AI_MODEL=qwen3:8b` override | COMPLETED; 13 PASS, 0 AI tests, 0 findings; about 67 seconds | Installed model did not complete planning within the configured 45-second request timeout |
| Retained evidence integrity | 56/56 files matched recorded SHA-256 and byte size for the current-configuration demo | Artifacts survive sandbox cleanup |
| Sandbox cleanup | No managed containers remained after both local audit runs | No orphan observed at this checkpoint |
| Existing workspace evidence | Both listed sample artifacts returned HTTP 200 | Screenshot and trace can be downloaded; this does not establish provenance of the seeded run |

Do not add the default and Docker backend counts together: they largely cover the same tests. The first frontend attempt had 13 passes and two failures while the backend was stopped. Starting the backend produced 15 passes. One supposedly mocked download test depends on backend behavior because the browser download bypasses its page interception; this is a test isolation weakness, not a confirmed real-download defect.

**What works**

| Area | Current assessment |
|---|---|
| Welcome page / workspace navigation | Functional; desktop and mobile captures inspected. The visual design is coherent enough for a presentation. |
| New-run form | URL validation, discovery versus testing selection, successful submission handling and API errors pass browser contract tests. |
| Run history / projects / preferences | Navigation, pagination/current-page filters and persisted motion preference pass. Projects intentionally derives from recent runs. |
| Run detail tabs | Application map, strategy, test plan, results, evidence, logs and analysis render; logs can be filtered. |
| Cancellation | Browser API contract and backend/Docker cancellation tests pass. |
| Local Git fixture → Node build → browser discovery | Confirmed in fresh independent demo runs. Discovery correctly recorded six pages, including the broken checkout route as HTTP 404. |
| Deterministic UI/API execution | Existing real Docker integration tests pass. The independent demo generated and executed 13 baseline tests. |
| Failure analysis plumbing | Mock-provider integration coverage passes and stored analysis renders. Live model-generated findings were not obtained in this audit. |
| Evidence | Screenshots, traces, logs and metadata persist. Download of an existing artifact passed the live frontend test. |
| Failure fallback | Missing or slow AI does not crash the run. The weakness is how that reduced coverage is communicated. |

**Problems to fix, in priority order**

| Priority | Finding and evidence | Required change and acceptance condition |
|---|---|---|
| P0 | **A broken route passes QA.** Discovery recorded `/checkout-broken` with status 404 and `http_error`, but `Internal route /checkout-broken loads` passed. Navigation baselines assert only document readiness and URL matching. See `backend/app/services/baseline_generator.py:93` and `backend/testq_browser/test_runner.py:343`. | Add an appropriate HTTP success assertion to navigation baselines and verify destination behavior for click navigation. Ensure the HTTP status represents the destination, not a previous `goto`. Acceptance: broken checkout reliably fails; the corrected route passes. Preserve a regression test exercising a real 404 response. |
| P0 | **Configured AI is unavailable.** Runtime settings request `llama3.1`; Ollama returns `model 'llama3.1' not found`. The real planner/generator test fails. | Select an installed model, verify a structured planning request before enabling the run, and show a clear model-specific error. Changing to `qwen3:8b` alone was insufficient in the measured attempt. |
| P0 | **Installed-model generation misses the deadline.** With only the model override, planning timed out after 45 seconds and generated zero AI tests. | Measure warm and cold generation, prewarm before presentation, reduce observation/prompt size and requested output, then choose a model and bounded timeout this laptop can satisfy. Acceptance: three consecutive complete demo runs with nonzero validated AI tests and measured durations fitting the presentation. Do not just raise timeouts without measuring. |
| P0 | **Reduced coverage looks successful.** Both fresh demo runs show COMPLETED and 13 passes, although AI was skipped and no defect was found. AI warnings are retained in logs. `/health` reports backend availability only. | Add explicit AI status and a visible 'baseline only / AI unavailable or timed out' banner beside run results. Separate execution completion from coverage and application verdict. Show Docker/image/model readiness before Start run. |
| P0 | **Workspace showcase is seeded data.** The only pre-existing run is `demo-run-juice-shop`, matching `backend/seed_demo_run.py`; its commit, counters and findings are inserted by that script. | Label sample runs prominently and exclude them from real-run metrics, or replace the showcase with a genuinely executed retained run. Never describe seeded findings as live discoveries. |
| P1 | **The intended demo bugs are not reliably covered.** Both independent live-model attempts found none. Many baseline checks assert visibility/readiness rather than business behavior. The demo E2E test supplies a mocked AI test and mocked analysis. | Keep explicit deterministic regression cases for broken checkout navigation, quantity zero and invalid email. Label those authored baselines honestly; show separately what the live AI adds. Prove bug detection and then the same tests passing against a fixed version. |
| P1 | **Local demo is not directly startable through the normal form.** The form/API accepts public GitHub repository URLs; the local audit needed a Git fixture harness. | Publish a dedicated demo repository if desired, or add an explicitly scoped local demo launcher. Acceptance: start the chosen demo from the website and finish without a terminal-only fixture. Publishing was not performed by this audit. |
| P1 | **Finding-to-evidence navigation is incomplete.** Analysis renders summary, root cause and reproduction, but does not render the API's `evidence_references` as links. | Link each finding to its exact failed assertion, result, screenshot and trace; do not make judges hunt across unrelated tabs. Add a compact expected-versus-actual view. |
| P1 | **No concise presentation/report export flow was found.** Raw evidence downloads work, but a judge-facing run summary is absent. | Add a single HTML/printable summary: repository + commit, coverage, AI status, actual failures, reproduction and evidence links. This is more valuable for the demo than additional decorative animation. |
| P2 | **Browser hardening differs across phases.** The execution runner passes `--no-sandbox` despite also setting `chromium_sandbox=True` (`backend/testq_browser/test_runner.py:142`). | Review and validate the effective browser sandbox configuration. Docker isolation still exists; avoid claiming every browser phase uses Chromium sandboxing until verified. |
| P2 | **Scope and operational limitations need clear presentation.** Single-process/local design, no multi-user authentication, no multi-service orchestration; external-service-dependent apps may fail under loopback-only runtime. | Present the supported scope accurately. Keep local demo deployment; multi-user hosting and broad framework coverage can wait. |

**Minimum hackathon-ready plan**

1. Fix the 404 false pass and add reproducible tests for the three intentional demo defects. This is the first credibility gate.
2. Make model readiness and AI fallback visible; get live generation reliably within the measured presentation budget.
3. Establish one honest, repeatable website-triggered demo. Save a real successful run, with its commit and complete evidence, as an explicitly labeled replay backup.
4. Add direct finding → failed assertion → screenshot/trace navigation and a one-page summary.
5. Rehearse the same demo three times on the presentation laptop. Include a cold start, warm model, missing-model case, cancel, and a restart followed by reopening evidence. Require no orphan containers and no unexplained missing artifacts.
6. Freeze the validated version and capture a short backup recording. Avoid broad feature expansion until this core loop is dependable.

The minimum live story should be: introduce the problem → start the known demo → show the real application map → show a defect and exact evidence → show reproduction → rerun a corrected version and compare. A prepared replay is useful if labeled; it must not be represented as new execution. The strongest technical distinction already present is that the model proposes structured tests while deterministic code executes them in an isolated environment with retained evidence.

**Suggested three-minute presentation**

| Time | Demonstration |
|---|---|
| 0:00–0:25 | Explain the gap between generating an application and independently verifying its behavior. State the supported scope. |
| 0:25–0:55 | Submit the controlled repository; show environment readiness and real stage progress. |
| 0:55–1:35 | Show the app map, baseline versus AI test origin, and the actual failing checkout assertion. Use a clearly labeled completed real run if execution exceeds this window. |
| 1:35–2:15 | Open the linked screenshot/trace, expected versus actual, and reproduction steps. Treat AI root cause as a hypothesis. |
| 2:15–2:45 | Compare broken and fixed commits using the same regression test. |
| 2:45–3:00 | State measured outcomes and next scope: supported apps, elapsed time, detected defects and retained evidence. |

A reliable demonstrated failure and fix will support the pitch better than claiming universal autonomous QA. Winning depends on the event's criteria and competing entries; the acceptance gates above make this project's core claim demonstrable.

**Evidence and reproducibility**

- [Default backend test results](evidence/qa-backend.xml)
- [Full Docker/live-model test results](evidence/qa-backend-docker.xml)
- [Public GitHub test results](evidence/qa-public.xml)
- [Public repository commit and artifact manifest](evidence/hackathon-public/public-verification.json)
- [Fresh demo with configured model](evidence/hackathon-audit/live-demo-configured-model.json)
- [Fresh demo with installed-model override](evidence/hackathon-audit/live-demo.json)
- [Configured-model console log](evidence/hackathon-configured-model.log)
- [Installed-model console log](evidence/hackathon-qwen.log)
- [Independent audit harness](backend/qa_hackathon_audit.py)
- [Desktop workspace screenshot](frontend/test-results/live-desktop.png)
- [Run log screenshot](frontend/test-results/live-run.png)
- [Mobile welcome screenshot after scrolling](frontend/test-results/welcome-expanded-390.png)

Audit run IDs: current configuration `174be541-1c89-4d5d-b465-edf40aed5ac4`; installed-model override `9442f42c-67a7-49cd-93f5-6592b29f0d37`. An earlier harness setup attempt cloned the wrong fixture source and failed during installation; that harness issue was corrected before the two reported demo runs and is not counted as a product finding.

Coverage limits: Chromium only; no Safari/Firefox/device-lab testing, concurrency/load testing, comprehensive penetration testing, or full accessibility certification. The browser suite's create/cancel flows use intercepted API responses; Docker pipeline tests cover execution separately. The fresh local demos were launched by the audit harness, not the public-GitHub website form. Live AI findings and a complete broken-versus-fixed demo remain unverified.
