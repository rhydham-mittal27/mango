"""without_mango.py — plain FastAPI + SQLAlchemy, the way this router
gets hand-written in a typical project. This is your original pasted
code, reformatted only (no logic changed) so it lines up 1:1 against
with_mango.py for comparison. 124 lines.
"""
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import User, Project, ProjectMember
from app.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    PaginatedProjects,
)
from app.security import decode_token
from app.permissions import require_role

router = APIRouter(prefix="/projects", tags=["Projects"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(token)

    user = await db.scalar(select(User).where(User.id == payload["sub"]))

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return user


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async with db.begin():
        project = Project(
            name=data.name,
            description=data.description,
            owner_id=current_user.id,
        )
        db.add(project)
        await db.flush()

        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=current_user.id,
                role="owner",
            )
        )

    await db.refresh(project)
    return project


@router.get("", response_model=PaginatedProjects)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    search: str | None = None,
):
    stmt = (
        select(Project)
        .join(ProjectMember)
        .where(ProjectMember.user_id == current_user.id)
        .options(selectinload(Project.members))
    )

    if search:
        stmt = stmt.where(
            or_(
                Project.name.ilike(f"%{search}%"),
                Project.description.ilike(f"%{search}%"),
            )
        )

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))

    stmt = stmt.offset((page - 1) * limit).limit(limit).order_by(Project.created_at.desc())

    projects = (await db.scalars(stmt)).all()

    return PaginatedProjects(total=total, page=page, limit=limit, items=projects)


@router.put("/{project_id}")
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await db.scalar(
        select(Project).options(selectinload(Project.members)).where(Project.id == project_id)
    )

    if not project:
        raise HTTPException(404, "Project not found")

    require_role(current_user.id, project.members, ["owner", "admin"])

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    project.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(project)

    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await db.scalar(
        select(Project).options(selectinload(Project.members)).where(Project.id == project_id)
    )

    if not project:
        raise HTTPException(404)

    require_role(current_user.id, project.members, ["owner"])

    await db.delete(project)
    await db.commit()

    return {"message": "Project deleted successfully"}
