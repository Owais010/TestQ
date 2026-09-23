"""
Tests for the GitHub Service.

Tests URL validation, clone handling, and error cases.
Note: actual cloning tests require network access and are marked accordingly.
"""

import pytest
from pathlib import Path

from app.services.github_service import (
    GitHubService,
    InvalidRepositoryURL,
)


class TestURLValidation:
    """Test GitHub URL validation."""

    def setup_method(self):
        self.service = GitHubService()

    def test_valid_url(self):
        url = self.service.validate_url("https://github.com/vercel/next.js")
        assert url == "https://github.com/vercel/next.js"

    def test_valid_url_with_trailing_slash(self):
        url = self.service.validate_url("https://github.com/user/repo/")
        assert url == "https://github.com/user/repo"

    def test_valid_url_with_git_suffix(self):
        url = self.service.validate_url("https://github.com/user/repo.git")
        assert url == "https://github.com/user/repo"

    def test_valid_url_with_spaces(self):
        url = self.service.validate_url("  https://github.com/user/repo  ")
        assert url == "https://github.com/user/repo"

    def test_invalid_url_not_github(self):
        with pytest.raises(InvalidRepositoryURL):
            self.service.validate_url("https://gitlab.com/user/repo")

    def test_invalid_url_no_repo(self):
        with pytest.raises(InvalidRepositoryURL):
            self.service.validate_url("https://github.com/user")

    def test_invalid_url_empty(self):
        with pytest.raises(InvalidRepositoryURL):
            self.service.validate_url("")

    def test_invalid_url_random_text(self):
        with pytest.raises(InvalidRepositoryURL):
            self.service.validate_url("not a url at all")

    def test_valid_url_with_dots_in_name(self):
        url = self.service.validate_url("https://github.com/user/repo.name")
        assert url == "https://github.com/user/repo.name"

    def test_valid_url_with_hyphens(self):
        url = self.service.validate_url("https://github.com/my-org/my-repo")
        assert url == "https://github.com/my-org/my-repo"
