"""
Project API routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.github_service import GitHubService, InvalidRepositoryURL

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project from a GitHub repository URL."""
    # Validate URL
    github = GitHubService()
    try:
        validated_url = github.validate_url(data.repository_url)
    except InvalidRepositoryURL as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if project already exists
    result = await db.execute(
        select(Project).where(Project.repository_url == validated_url)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Create new project
    project = Project(
        repository_url=validated_url,
        default_branch=data.branch or "",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get project details by ID."""
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
