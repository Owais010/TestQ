"""Phase 1 orchestration with a single structured owner for every run resource."""
import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import settings
from app.models.test_run import TestRun, TestRunStatus as S
from app.models.log import Log
from app.models.discovery import Evidence
from app.schemas.common import SandboxConfig
from app.services.github_service import GitHubService
from app.services.project_detector import detect_project
from app.services.sandbox_manager import SandboxManager, SandboxError
from app.services.build_manager import BuildManager
from app.services.health_checker import HealthChecker
from app.services.discovery_service import DiscoveryService
from app.services.baseline_generator import BaselineGenerator
from app.services.demo_showcase import is_demo_repo, create_demo_deterministic_tests
from app.services.static_analyzer import StaticAnalyzer
from app.services.runtime_monitor import RuntimeMonitor
from app.services.test_executor import TestExecutor
from app.ai import (
    get_ai_provider, AIError, AIUnavailableError, AITimeoutError,
    AISchemaValidationError, AIInvalidOutputError,
)
from app.services.test_planner import TestPlanner
from app.services.test_generator import TestGenerator
from app.services.failure_analyzer import FailureAnalyzer
from app.models.failure_analysis import FailureAnalysisRecord
from testq_browser.policies import redact
from app.worker.control import RunControl, RunCancelled, controls


logger = logging.getLogger("testq.pipeline")
NODE_SANDBOX_IMAGE = "testq-sandbox-node:latest"
PYTHON_SANDBOX_IMAGE = "testq-sandbox-python:latest"
STAGES = [S.CLONING, S.ANALYZING, S.BUILDING, S.STARTING, S.READY,
          S.TESTING, S.ANALYZING_FAILURES, S.COMPLETED]
KEYS = ["cloning", "analyzing", "building", "starting", "ready",
        "testing", "analyzing_failures", "report"]


class InvalidTransition(ValueError):
    pass


class Pipeline:
    def __init__(self, db, control=None, sandbox_factory=SandboxManager, github=None, ai_provider=None):
        self.db = db
        self.control = control or RunControl(settings.run_timeout)
        self.sandbox_factory = sandbox_factory
        self.sandbox = None
        self.discovery = None
        self.github = github or GitHubService(control=self.control)
        self.github.control = self.control
        self.health_checker = HealthChecker()
        self.ai_provider = ai_provider

    async def _blocking(self, function, *args, **kwargs):
        # Shield the thread and JOIN on task cancellation; never orphan a create/exec.
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.control.cancel()
            try:
                await task
            except Exception:
                pass
            raise RunCancelled("Worker task cancelled")

    async def run(self, run):
        run_id = run.id
        controls[run_id] = self.control
        repo_path = None
        container_id = None
        outcome = S.READY
        cleanup_errors = []
        try:
            if run.testing_enabled and not run.discovery_enabled:
                raise ValueError("Testing requires discovery to be enabled")
            if run.cancellation_requested:
                self.control.cancel()
            self.control.check()
            run.started_at = datetime.now(timezone.utc)
            await self._update_status(run, S.CLONING)
            # Reserve path before git starts, so failure/cancellation also cleans it.
            repo_path = self.github.workspaces_dir / run.id
            project = getattr(run, "project", None) or await self.db.get(Project, run.project_id)
            repo_url = project.repository_url if project else ""
            clone = await self._blocking(
                self.github.clone_repository, repo_url,
                branch=run.branch or None, target_dir=repo_path,
            )
            if not run.branch:
                run.project.default_branch = clone["branch"]
            run.commit_sha, run.branch = clone["commit_sha"], clone["branch"]
            await self._log(run, "clone", "INFO", f"Cloned {run.branch} at {run.commit_sha}")
            await self._update_status(run, S.ANALYZING)
            config = await self._blocking(detect_project, repo_path)
            run.detected_config = config.model_dump()
            run.project.detected_framework = config.framework
            run.project.detected_language = config.language
            run.project.detected_package_manager = config.package_manager
            # Practical static analysis
            try:
                static_res = await self._blocking(StaticAnalyzer.analyze_project, repo_path)
                run.static_findings = static_res
                await self._log(run, "static_analyzer", "INFO", f"Static analysis identified {static_res.get('total', 0)} static findings")
            except Exception as se:
                await self._log(run, "static_analyzer", "WARN", f"Static analysis skipped: {se}")
            await self._update_status(run, S.BUILDING)
            self.sandbox = await self._blocking(self.sandbox_factory, self.control, run.id)
            image = PYTHON_SANDBOX_IMAGE if config.language == "python" else NODE_SANDBOX_IMAGE
            if not await self._blocking(self.sandbox.image_exists, image):
                raise SandboxError(f"Missing hardened image {image}; rebuild sandbox images before running TestQ")
            browser_needed = run.discovery_enabled or run.testing_enabled
            if browser_needed and not await self._blocking(self.sandbox.browser_available, image):
                raise SandboxError(f"Missing browser tooling in {image}; rebuild the Phase 2 sandbox image")
            info = await self._blocking(self.sandbox.create, SandboxConfig(
                image=image, cpu_limit=settings.docker_cpu_limit,
                memory_limit=settings.docker_memory_limit, timeout=self.control.remaining,
                browser_enabled=browser_needed,
            ), repo_path)
            container_id = info["container_id"]
            run.container_id = container_id
            await self._log(run, "sandbox", "INFO", f"Created sandbox {container_id}")
            builder = BuildManager(self.sandbox)
            await self._blocking(builder.install_dependencies, container_id, config)
            self.control.check()
            await self._blocking(builder.build_project, container_id, config)
            self.control.check()
            # No public interface or outbound network is needed after setup.
            await self._blocking(self.sandbox.restrict_network, container_id)
            await self._update_status(run, S.STARTING)
            exec_id = await self._blocking(builder.start_application, container_id, config)
            health = await self.health_checker.check_sandbox(
                self.sandbox, container_id, config.expected_port, self.control, self._blocking,
                exec_id=exec_id,
            )
            if not health.is_healthy:
                raise SandboxError(f"Health check failed: {health.error}")
            self.control.check()
            health_msg = f"HEALTH CHECK: {health.details or f'HTTP {health.status_code}'} - Status: READY (at {health.url})"
            await self._log(run, "startup", "INFO", health_msg)
            if run.discovery_enabled:
                await self._update_status(run, S.READY)
                await self._update_status(run, S.DISCOVERING)
                self.discovery = DiscoveryService(self.db, self.sandbox, container_id,
                                                  self.control, self._blocking)
                base_url = f"http://127.0.0.1:{config.expected_port}"
                result = await self.discovery.discover(base_url, run.id)
                await self._log(run, "discovery", "INFO", f"Discovery recorded {len(result.pages)} pages")

                if run.testing_enabled:
                    await self._update_status(run, S.TESTING)
                    is_demo = is_demo_repo(run.project.repository_url)
                    await self._log(run, "testing", "INFO", "Generating deterministic baseline test suite")
                    baseline_suite = BaselineGenerator.generate_suite(result, run.id)

                    demo_suite = []
                    if is_demo:
                        demo_suite = create_demo_deterministic_tests(run.id)
                        await self._log(run, "testing", "INFO", f"Injected {len(demo_suite)} deterministic showcase tests for demo application")

                    # AI Preflight and health check
                    ai_tests: list = []
                    ai_eligible = getattr(settings, "ai_enabled", True)
                    ai_prov = None
                    if ai_eligible:
                        try:
                            ai_prov = self.ai_provider or get_ai_provider()
                            raw_model = getattr(ai_prov, "model", settings.ai_model)
                            run.ai_model = str(raw_model) if isinstance(raw_model, str) else settings.ai_model
                            preflight_res = await ai_prov.preflight()
                            raw_status = getattr(preflight_res, "status", "READY")
                            status_str = str(raw_status) if isinstance(raw_status, str) else "READY"
                            run.ai_status = status_str
                            if status_str != "READY":
                                raw_msg = getattr(preflight_res, "message", "Model degraded")
                                msg_str = str(raw_msg) if isinstance(raw_msg, str) else "Model degraded"
                                run.ai_warning = f"Deterministic testing proceeding, but AI engine degraded ({status_str}): {msg_str}"
                                await self._log(run, "ai_preflight", "WARN", run.ai_warning)
                                ai_eligible = False
                            else:
                                await self._log(run, "ai_preflight", "INFO", f"AI preflight check successful ({run.ai_model} is READY)")
                        except Exception as p_err:
                            run.ai_status = "UNAVAILABLE"
                            run.ai_warning = f"Deterministic testing proceeding, but AI engine unavailable: {p_err}"
                            await self._log(run, "ai_preflight", "WARN", run.ai_warning)
                            ai_eligible = False
                    else:
                        run.ai_status = "NOT_REQUESTED"

                    if ai_eligible and ai_prov:
                        try:
                            self.control.check()
                            await self._log(run, "ai_planner", "INFO", "Starting AI Test Planning")
                            planner = TestPlanner(ai_prov)
                            strategy = await planner.plan(result, config)
                            await self._log(run, "ai_planner", "INFO", f"AI Test Planning produced {len(strategy.items)} strategy items")
                            await self._log(run, "ai_strategy", "INFO", json.dumps(strategy.model_dump(mode="json")))

                            self.control.check()
                            await self._log(run, "ai_generator", "INFO", "Starting AI Test Generation")
                            generator = TestGenerator(ai_prov)
                            ai_tests = await generator.generate(strategy, result, run.id, baseline_cases=baseline_suite)
                            await self._log(run, "ai_generator", "INFO", f"AI Test Generation produced {len(ai_tests)} validated tests")
                        except (AISchemaValidationError, AIInvalidOutputError) as schema_err:
                            run.ai_status = "DEGRADED"
                            run.ai_warning = f"AI TEST GENERATION FAILED. Reason: Generated output did not satisfy TestQ's executable test schema ({schema_err}). Deterministic tests continued."
                            await self._log(run, "ai_generator", "WARN", run.ai_warning)
                        except (AIUnavailableError, AITimeoutError) as ai_err:
                            run.ai_status = "DEGRADED"
                            run.ai_warning = f"Deterministic testing completed, but AI-generated adversarial tests were unavailable ({ai_err})."
                            await self._log(run, "ai_generator", "WARN", run.ai_warning)
                        except Exception as err:
                            run.ai_status = "DEGRADED"
                            run.ai_warning = f"AI TEST GENERATION FAILED: {err}. Deterministic tests continued."
                            await self._log(run, "ai_generator", "WARN", run.ai_warning)

                    run.ai_test_count = len(ai_tests)
                    if len(ai_tests) == 0 and not run.ai_warning:
                        run.ai_status = "DEGRADED"
                        run.ai_warning = "AI TEST GENERATION FAILED. Reason: 0 valid tests produced. Deterministic tests continued."

                    combined_suite = list(baseline_suite) + list(demo_suite) + ai_tests
                    if len(combined_suite) > settings.max_tests_per_run:
                        combined_suite = combined_suite[:settings.max_tests_per_run]

                    for tc in combined_suite:
                        self.db.add(tc)
                    await self.db.commit()

                    await self._log(run, "testing", "INFO", f"Executing {len(combined_suite)} tests ({len(baseline_suite)} baseline, {len(demo_suite)} demo deterministic, {len(ai_tests)} AI-generated)")
                    executor = TestExecutor(self.db, self.sandbox, container_id, self.control, self._blocking)
                    test_results = await executor.execute_suite(
                        base_url=base_url,
                        run_id=run.id,
                        session_id=result.session_id,
                        test_cases=combined_suite,
                    )
                    passed_count = sum(1 for r in test_results if r.status == "PASS")
                    await self._log(run, "testing", "INFO", f"Deterministic testing complete: {passed_count}/{len(test_results)} passed")

                    # Runtime Monitor observations
                    runtime_mon = RuntimeMonitor(run.id)
                    for tr in test_results:
                        if tr.error:
                            runtime_mon.observe(
                                kind="http_error" if getattr(tr, "http_status", 0) and tr.http_status >= 400 else "assertion_error",
                                source="browser" if getattr(tr, "http_status", 0) is None else "server",
                                severity="error",
                                message=tr.error,
                                test_id=tr.test_case_id,
                            )
                    run.observations = [o.model_dump() for o in runtime_mon.observations]
                    await self.db.commit()

                    # Phase 4.5: AI Failure Analysis & Evidence Linkage on failed/errored/timed-out tests
                    failed_results = [r for r in test_results if r.status in ("FAIL", "ERROR", "TIMEOUT")]
                    if failed_results:
                        await self._update_status(run, S.ANALYZING_FAILURES)
                        await self._log(run, "failure_analyzer", "INFO", f"Starting failure analysis on {len(failed_results)} failed test(s)")
                        tc_map = {tc.id: tc for tc in combined_suite}
                        analyzer = None
                        if ai_eligible and ai_prov and run.ai_status != "UNAVAILABLE":
                            try:
                                analyzer = FailureAnalyzer(ai_prov)
                            except Exception:
                                analyzer = None

                        for fres in failed_results:
                            self.control.check()
                            tc = tc_map.get(fres.test_case_id)
                            if not tc:
                                continue

                            # Query actual Evidence rows for this test result
                            ev_rows = (await self.db.execute(
                                select(Evidence).where(Evidence.run_id == run.id, Evidence.test_result_id == fres.id)
                            )).scalars().all()
                            evidence_api_urls = [f"/api/test-runs/{run.id}/evidence/{e.id}" for e in ev_rows]
                            evidence_items_for_ai = [{"path": e.path} for e in ev_rows]
                            if not evidence_items_for_ai:
                                evidence_items_for_ai = [{"path": f"evidence/{run.id}/testing/{fres.id}/screenshot.png"}]

                            # AI Analysis if analyzer is available
                            analysis = None
                            if analyzer:
                                try:
                                    analysis = await analyzer.analyze_failure(
                                        test_case_data={
                                            "id": tc.id,
                                            "type": tc.type,
                                            "title": tc.title,
                                            "priority": tc.priority,
                                            "source": getattr(tc, "source", "baseline"),
                                            "definition": tc.definition,
                                        },
                                        test_result_data={
                                            "status": fres.status,
                                            "duration_ms": fres.duration_ms,
                                            "error": fres.error,
                                            "expected": fres.expected,
                                            "actual": fres.actual,
                                            "steps_json": fres.steps_json,
                                            "assertions_json": fres.assertions_json,
                                        },
                                        evidence_items=evidence_items_for_ai,
                                        discovery_observations=result.raw_data if hasattr(result, "raw_data") else None,
                                    )
                                except Exception as a_err:
                                    await self._log(run, "failure_analyzer", "WARN", f"AI failure analysis error for {tc.title}: {a_err}")

                            # Evidence-based classification
                            err_str = (fres.error or "").lower()
                            if any(k in err_str for k in ["econnrefused", "connection refused", "sandbox", "sigkill", "sigterm", "502", "503"]):
                                classification = "ENVIRONMENT FAILURE"
                            elif getattr(fres, "confirmed", False) or getattr(fres, "reproduction_count", 0) >= 2:
                                classification = "CONFIRMED BUG"
                            elif fres.status == "TIMEOUT" or "timeout" in err_str:
                                classification = "TEST FAILURE"
                            else:
                                classification = "POSSIBLE BUG"

                            rec = FailureAnalysisRecord(
                                run_id=run.id,
                                test_result_id=fres.id,
                                test_case_id=tc.id,
                                title=analysis.title if analysis else f"Defect: {tc.title}",
                                severity=analysis.severity.value if analysis and hasattr(analysis.severity, "value") else (str(analysis.severity) if analysis else ("critical" if classification == "CONFIRMED BUG" else "high")),
                                category=analysis.category.value if analysis and hasattr(analysis.category, "value") else (str(analysis.category) if analysis else "functional"),
                                summary=analysis.summary if analysis else (fres.error or "Test assertion failed."),
                                likely_root_cause=analysis.likely_root_cause if analysis else "Application route or input validation returned an unexpected response.",
                                reproduction_steps=analysis.reproduction_steps if analysis else [f"Execute test case {tc.title}", f"Observe result: {fres.error}"],
                                evidence_references=evidence_api_urls if evidence_api_urls else [f"/api/test-runs/{run.id}/evidence"],
                                confidence=analysis.confidence if analysis else (0.95 if classification == "CONFIRMED BUG" else 0.7),
                                reproduction_count=getattr(fres, "reproduction_count", 1),
                                reproduction_total=getattr(fres, "reproduction_total", 3),
                                classification=classification,
                            )
                            self.db.add(rec)
                            await self.db.commit()
                            await self._log(run, "failure_analyzer", "INFO", f"Recorded [{rec.classification} - {rec.severity.upper()}]: {rec.title} ({rec.reproduction_count}/{rec.reproduction_total} repro)")

                    self.control.check()
                    outcome = S.COMPLETED
                else:
                    outcome = S.DISCOVERY_COMPLETE
        except (RunCancelled, asyncio.CancelledError) as error:
            self.control.cancel()
            outcome = S.CANCELLED
            run.failure_reason = str(error) or "Worker cancelled"
            run.failure_stage = run.status
        except Exception as error:
            outcome = S.CANCELLED if self.control.cancel_event.is_set() else S.FAILED
            run.failure_reason = str(error) or repr(error)
            run.failure_stage = run.status
            logger.exception("Run %s failed", run_id)
            try:
                await self.db.rollback()
            except Exception:
                pass
        finally:
            # Logging or DB failure must never bypass resource cleanup.
            try:
                if self.sandbox and container_id:
                    await self._blocking(self.sandbox.kill, container_id)
                    for source, stream, value in await self._blocking(self.sandbox.collect_logs, container_id):
                        # Chunk to keep individual DB records/API objects manageable.
                        for offset in range(0, len(value), 65536):
                            await self._log(run, source, "ERROR" if stream == "stderr" else "INFO",
                                            f"[{stream}] {value[offset:offset+65536]}")
                    if self.discovery:
                        await self.discovery.attach_application_logs()
            except Exception as error:
                cleanup_errors.append(f"Log retention: {error}")
            finally:
                if self.sandbox:
                    try:
                        await self._blocking(self.sandbox.cleanup)
                        run.container_id = None
                        run.sandbox_port = None
                    except Exception as error:
                        cleanup_errors.append(f"Sandbox cleanup: {error}")
                if repo_path:
                    try:
                        await self._blocking(self.github.cleanup_workspace, repo_path)
                    except Exception as error:
                        cleanup_errors.append(f"Workspace cleanup: {error}")
            try:
                if self.control.cancel_event.is_set():
                    outcome = S.CANCELLED
                if cleanup_errors:
                    outcome = S.CANCELLED if outcome == S.CANCELLED else S.FAILED
                    run.failure_reason = (run.failure_reason or "") + "; " + "; ".join(cleanup_errors)
                    run.failure_stage = run.failure_stage or "CLEANUP"
                if outcome == S.CANCELLED:
                    run.failure_reason = run.failure_reason or "Cancelled by user"
                    run.cancellation_requested = True
                run.finished_at = datetime.now(timezone.utc)
                try:
                    await self._update_status(run, outcome)
                except RunCancelled:
                    run.cancellation_requested = True
                    run.failure_reason = "Cancelled by user"
                    run.finished_at = datetime.now(timezone.utc)
                    await self._update_status(run, S.CANCELLED)
                success = outcome in (S.READY, S.DISCOVERY_COMPLETE, S.COMPLETED)
                message = ("Deterministic testing complete; results and evidence retained; sandbox cleaned up"
                           if outcome == S.COMPLETED else (
                               "Discovery complete; evidence retained; sandbox and workspace removed"
                               if outcome == S.DISCOVERY_COMPLETE else "Phase 1 READY; sandbox and workspace removed"
                           ))
                await self._log(run, "system", "INFO" if success else "ERROR",
                                getattr(run, "failure_reason", None) or message)
            finally:
                self.control.done.set()
                controls.pop(run_id, None)

    async def _update_status(self, run, new_status):
        row = (await self.db.execute(select(TestRun).where(TestRun.id == run.id))).scalar_one_or_none()
        if not row:
            return
        old_status = row.status
        if not row.can_transition_to(new_status):
            raise InvalidTransition(f"Invalid state transition: {old_status} -> {new_status}")
        if new_status not in S.TERMINAL:
            self.control.check()
        progress = dict(row.progress or {})
        if new_status in (S.FAILED, S.CANCELLED):
            if old_status == S.DISCOVERING:
                progress["discovering"] = new_status.lower()
            elif old_status == S.TESTING:
                progress["testing"] = new_status.lower()
            if old_status in STAGES:
                progress[KEYS[STAGES.index(old_status)]] = new_status.lower()
        elif new_status in (S.DISCOVERING, S.DISCOVERY_COMPLETE):
            progress["ready"] = "completed"
            progress["discovering"] = "completed" if new_status == S.DISCOVERY_COMPLETE else "in_progress"
            if new_status == S.DISCOVERY_COMPLETE:
                progress["discovery_complete"] = "completed"
        elif new_status == S.TESTING:
            progress["ready"] = "completed"
            progress["discovering"] = "completed"
            progress["testing"] = "in_progress"
        elif new_status == S.COMPLETED:
            progress["ready"] = "completed"
            progress["discovering"] = "completed"
            progress["testing"] = "completed"
            progress["analyzing_failures"] = "completed"
            progress["report"] = "completed"

        else:
            index = STAGES.index(new_status)
            for key in KEYS[:index]:
                progress[key] = "completed"
            progress[KEYS[index]] = "completed" if new_status in (S.READY, S.COMPLETED) else "in_progress"
        await self.db.flush()
        condition = [TestRun.id == run.id, TestRun.status == old_status]
        if new_status != S.CANCELLED:
            condition.append(TestRun.cancellation_requested.is_(False))

        update_vals = {
            "status": new_status,
            "progress": progress,
        }
        if new_status in S.TERMINAL:
            update_vals["finished_at"] = datetime.now(timezone.utc)
            if getattr(run, "failure_reason", None):
                update_vals["failure_reason"] = run.failure_reason
            if getattr(run, "failure_stage", None):
                update_vals["failure_stage"] = run.failure_stage
            if getattr(run, "ai_status", None):
                update_vals["ai_status"] = run.ai_status
            if getattr(run, "ai_warning", None):
                update_vals["ai_warning"] = run.ai_warning
            if getattr(run, "ai_test_count", None) is not None:
                update_vals["ai_test_count"] = run.ai_test_count

        result = await self.db.execute(update(TestRun).where(*condition).values(
            **update_vals
        ).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            await self.db.rollback()
            await self.db.refresh(row)
            if row.cancellation_requested:
                self.control.cancel()
                raise RunCancelled("Cancellation requested")
            raise InvalidTransition("Run state changed concurrently")
        await self.db.commit()
        await self.db.refresh(run, ["status", "progress", "cancellation_requested"])

    async def _log(self, run, source, level, message):
        if run.discovery_enabled:
            message = redact(message, 65536)
        self.db.add(Log(run_id=run.id, source=source, level=level, message=message))
        await self.db.commit()
