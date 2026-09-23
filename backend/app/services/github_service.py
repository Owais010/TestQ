"""
GitHub Service.

Handles repository cloning, branch resolution, and URL validation.
Repository code is NEVER executed during cloning — only git operations.
"""

import logging
import os
import re
import shutil
from pathlib import Path

from git import Repo, GitCommandError, InvalidGitRepositoryError

from app.config import settings

logger = logging.getLogger("testq.github")

# Pattern to validate GitHub repository URLs
GITHUB_URL_PATTERN = re.compile(
    r"^https?://github\.com/[\w\-\.]+/[\w\-\.]+/?$"
)


class GitHubServiceError(Exception):
    """Base error for GitHub operations."""

    pass


class InvalidRepositoryURL(GitHubServiceError):
    """The provided URL is not a valid GitHub repository URL."""

    pass


class CloneError(GitHubServiceError):
    """Failed to clone the repository."""

    pass


class BranchError(GitHubServiceError):
    """The specified branch does not exist."""

    pass


class GitHubService:
    """Handles GitHub repository operations."""

    def __init__(self, workspaces_dir: Path | None = None):
        self.workspaces_dir = workspaces_dir or settings.workspaces_path

    def validate_url(self, url: str) -> str:
        """
        Validate and normalize a GitHub repository URL.

        Returns the cleaned URL.
        Raises InvalidRepositoryURL if invalid.
        """
        url = url.strip().rstrip("/")

        # Remove .git suffix if present
        if url.endswith(".git"):
            url = url[:-4]

        if not GITHUB_URL_PATTERN.match(url):
            raise InvalidRepositoryURL(
                f"Invalid GitHub repository URL: {url}. "
                "Expected format: https://github.com/owner/repo"
            )

        return url

    def clone_repository(
        self,
        repository_url: str,
        branch: str = "main",
        target_dir: Path | None = None,
    ) -> dict:
        """
        Clone a public GitHub repository.

        Args:
            repository_url: The GitHub repository URL.
            branch: Branch to checkout (default: main).
            target_dir: Where to clone. If None, creates a temp dir under workspaces.

        Returns:
            dict with repo_path, branch, commit_sha.

        Raises:
            InvalidRepositoryURL: If URL is invalid.
            CloneError: If cloning fails.
            BranchError: If branch doesn't exist.
        """
        url = self.validate_url(repository_url)

        if target_dir is None:
            # Extract repo name for directory naming
            parts = url.rstrip("/").split("/")
            repo_name = parts[-1] if parts else "repo"
            import uuid

            target_dir = self.workspaces_dir / f"{repo_name}_{uuid.uuid4().hex[:8]}"

        target_dir = Path(target_dir)

        # Clean up if directory already exists
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Cloning {url} (branch: {branch}) to {target_dir}")

        try:
            # Clone with depth=1 for speed (shallow clone)
            clone_url = url + ".git"
            repo = Repo.clone_from(
                clone_url,
                str(target_dir),
                branch=branch,
                depth=1,
                no_checkout=False,
            )
        except GitCommandError as e:
            error_msg = str(e)

            # Check for branch-not-found errors
            if "not found" in error_msg.lower() or "could not find" in error_msg.lower():
                # Try cloning default branch first, then checkout
                try:
                    repo = Repo.clone_from(
                        clone_url, str(target_dir), depth=1
                    )
                    # Try to checkout the requested branch
                    try:
                        repo.git.checkout(branch)
                    except GitCommandError:
                        shutil.rmtree(target_dir, ignore_errors=True)
                        raise BranchError(
                            f"Branch '{branch}' not found in {url}"
                        )
                except GitCommandError:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    raise CloneError(f"Failed to clone repository: {error_msg}")
            elif "repository not found" in error_msg.lower():
                shutil.rmtree(target_dir, ignore_errors=True)
                raise CloneError(
                    f"Repository not found: {url}. "
                    "Make sure it exists and is public."
                )
            else:
                shutil.rmtree(target_dir, ignore_errors=True)
                raise CloneError(f"Failed to clone repository: {error_msg}")

        # Get commit SHA
        try:
            commit_sha = repo.head.commit.hexsha
        except Exception:
            commit_sha = None

        logger.info(
            f"Cloned successfully: {target_dir} "
            f"(commit: {commit_sha[:8] if commit_sha else 'unknown'})"
        )

        return {
            "repo_path": str(target_dir),
            "branch": branch,
            "commit_sha": commit_sha,
        }

    def cleanup_workspace(self, repo_path: str | Path) -> None:
        """Remove a cloned repository workspace."""
        path = Path(repo_path)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"Cleaned up workspace: {path}")
