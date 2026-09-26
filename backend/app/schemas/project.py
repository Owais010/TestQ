"""Project API schemas."""

from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class ProjectCreate(BaseModel):
    """Request to create a project."""

    repository_url: str = Field(
        ...,
        description="GitHub repository URL",
        examples=["https://github.com/user/project"],
    )
    branch: str | None = Field(None, description="Branch to analyze; omitted uses remote default")


class ProjectResponse(BaseModel):
    """Project details response."""

    id: str
    repository_url: str
    default_branch: str
    detected_framework: str | None = None
    detected_language: str | None = None
    detected_package_manager: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
