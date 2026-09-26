"""Validated GitHub intake and cancellable git subprocesses (no repo execution)."""
import os
import re
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from app.config import settings, APP_ROOT
from app.worker.control import RunControl

GITHUB_URL_PATTERN = re.compile(r"^https?://github\.com/[\w\-.]+/[\w\-.]+/?$")


class GitHubServiceError(Exception):
    pass


class InvalidRepositoryURL(GitHubServiceError):
    pass


class CloneError(GitHubServiceError):
    pass


class BranchError(GitHubServiceError):
    pass


class GitHubService:
    def __init__(self, workspaces_dir=None, control: RunControl | None = None):
        self.workspaces_dir = Path(workspaces_dir or settings.workspaces_path).resolve()
        self.control = control

    def validate_url(self, url):
        url = url.strip().rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        if not GITHUB_URL_PATTERN.fullmatch(url):
            raise InvalidRepositoryURL(f"Invalid GitHub repository URL: {url}")
        return url

    def _git(self, args):
        control = self.control or RunControl(settings.docker_timeout)
        control.check()
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
        process = subprocess.Popen(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **options,
        )
        try:
            while True:
                control.check()
                try:
                    out, err = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
            raise
        if process.returncode:
            raise CloneError(err.decode("utf-8", errors="replace")[-4000:])
        return out.decode("utf-8", errors="replace").strip()

    def clone_repository(self, repository_url, branch=None, target_dir=None):
        url = self.validate_url(repository_url)
        if branch and (branch.startswith("-") or any(c.isspace() for c in branch)):
            raise BranchError("Invalid branch name")
        target = Path(target_dir or self.workspaces_dir / uuid.uuid4().hex).resolve()
        if not target.is_relative_to(self.workspaces_dir) or target == self.workspaces_dir:
            raise CloneError("Clone target must be inside the run workspace root")
        if target.exists():
            raise CloneError("Clone target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        demo_dir = (APP_ROOT / "demo").resolve()
        from app.services.demo_showcase import is_demo_repo
        if is_demo_repo(url) and demo_dir.exists():
            args = ["clone"]
            if branch:
                try:
                    branches = self._git(["-C", str(demo_dir), "branch", "--list", branch]).strip()
                    if branches:
                        args += ["--branch", branch]
                except Exception:
                    pass
            args += ["--", str(demo_dir), str(target)]
        else:
            args = ["clone", "--depth=1"]
            if branch:
                args += ["--branch", branch]
            args += ["--", url + ".git", str(target)]
        try:
            self._git(args)
            return {
                "repo_path": str(target),
                "branch": self._git(["-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"]),
                "commit_sha": self._git(["-C", str(target), "rev-parse", "HEAD"]),
            }
        except BaseException:
            self.cleanup_workspace(target)
            raise

    def cleanup_workspace(self, repo_path):
        path = Path(repo_path).resolve()
        if path == self.workspaces_dir or not path.is_relative_to(self.workspaces_dir):
            raise GitHubServiceError("Refusing cleanup outside workspace root")
        if path.exists():
            def writable_retry(function, item, error):
                os.chmod(item, 0o700)
                function(item)
            shutil.rmtree(path, onerror=writable_retry)
