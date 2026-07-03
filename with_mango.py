"""with_mango.py — the same router as without_mango.py, using mango.
No new syntax, just mango's existing library:
  - mango.Auth(verify_token=..., load_user=..., get_db=...).current_user()
    replaces BOTH module-level OAuth2PasswordBearer(...) AND the
    hand-written get_current_user() dependency in without_mango.py —
    declared once here, reused on every route via Depends(auth.current_user()).
  - mango.Router/Depends/Query are the literal FastAPI classes,
    re-exported under mango's name — no `import fastapi` needed.
  - _get_project_or_404() replaces the identical
    `if not project: raise HTTPException(404, ...)` block that
    without_mango.py repeats verbatim in update_project and delete_project.
  - require_role() is unchanged from the original — already a good,
    reusable helper, not boilerplate.
Everything else (the query building, the pagination math, the manual
setattr loop) is untouched real logic — same as without_mango.py,
line for line. 93 lines vs. 124.
"""
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import mango
from app.db import db
from app.models import Project, ProjectMember, User
from app.schemas import PaginatedProjects, ProjectCreate, ProjectResponse, ProjectUpdate
from app.security import decode_token

auth = mango.Auth(
    verify_token=decode_token,
    load_user=lambda session, claims: session.get(User, claims["sub"]),
    get_db=db.get_db,
)

router = mango.Router(prefix="/projects", tags=["Projects"])


def require_role(user: User, members: list[ProjectMember], roles: set[str]) -> None:
    """Raise 403 unless `user` holds one of `roles` on this project's membership list."""
    role = next((m.role for m in members if m.user_id == user.id), None)
    if role not in roles:
        raise mango.ForbiddenError("forbidden")


async def _get_project_or_404(session: AsyncSession, project_id: int) -> Project:
    """Fetch a project with its members eager-loaded, or 404 — the check
    both update_project and delete_project need before their role gate."""
    project = await session.scalar(
        select(Project).options(selectinload(Project.members)).where(Project.id == project_id)
    )
    if not project:
        raise mango.NotFoundError("Project not found")
    return project


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = mango.Depends(db.get_db),
    user: User = mango.Depends(auth.current_user()),
) -> Project:
    project = Project(**data.model_dump(), owner_id=user.id)
    session.add(project)
    await session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    await session.commit()
    await session.refresh(project)
    return project


@router.get("", response_model=PaginatedProjects)
async def list_projects(
    session: AsyncSession = mango.Depends(db.get_db),
    user: User = mango.Depends(auth.current_user()),
    page: int = mango.Query(1, ge=1),
    limit: int = mango.Query(20, le=100),
    search: str | None = None,
) -> PaginatedProjects:
    stmt = (
        select(Project)
        .join(ProjectMember)
        .where(ProjectMember.user_id == user.id)
        .options(selectinload(Project.members))
    )
    if search:
        stmt = stmt.where(
            or_(Project.name.ilike(f"%{search}%"), Project.description.ilike(f"%{search}%"))
        )

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await session.scalars(
            stmt.order_by(Project.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
    ).all()
    return PaginatedProjects(total=total, page=page, limit=limit, items=rows)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    session: AsyncSession = mango.Depends(db.get_db),
    user: User = mango.Depends(auth.current_user()),
) -> Project:
    project = await _get_project_or_404(session, project_id)
    require_role(user, project.members, {"owner", "admin"})

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    session: AsyncSession = mango.Depends(db.get_db),
    user: User = mango.Depends(auth.current_user()),
) -> dict:
    project = await _get_project_or_404(session, project_id)
    require_role(user, project.members, {"owner"})

    await session.delete(project)
    await session.commit()
    return {"message": "Project deleted successfully"}
