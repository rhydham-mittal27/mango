"""with_mango_easy.py — same router as with_mango.py, same line count
roughly, but restructured so each route READS easily, not just shorter.
The technique: push repeated *preconditions* (not just repeated code)
into named dependencies/helpers, so a route's body is left holding only
its own actual decision, and its signature tells you the precondition
without reading the body at all.

Three changes from with_mango.py, each targeting readability specifically:

  1. require_project(*roles) — a dependency FACTORY, not just a function.
     "fetch project by {project_id}, 404 if missing, 403 unless the
     caller holds one of these roles" was two imperative lines repeated
     in update_project/delete_project. As a dependency, it becomes part
     of the route's own signature:

         project: Project = mango.Depends(require_project("owner"))

     Reading that one line tells you the entire precondition — no need
     to read the function body to know who's allowed to call it.

  2. apply(obj, patch) / matches(term, *columns) / count_of(session, stmt)
     — three one-line helpers for shapes that appear once each here but
     read as noise inline: a setattr loop, an OR-of-ilikes, a COUNT(*)
     subquery. Naming them turns "here's how a partial update works"
     into "apply(project, data)" — the reader trusts the name and moves on.

  3. list_projects' query is still built as one fluent chain (that part
     WAS already clear — chaining reads like a sentence), but the
     search/count/page steps are now each a single, self-contained line
     instead of being spliced into the middle of the query construction.

None of this is new syntax — it's the same plain-Python + mango as
with_mango.py, just organized so the "what can happen here" question
is answerable from signatures and helper names alone.
"""
from datetime import datetime, timezone

from pydantic import BaseModel
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


# ── small named helpers — each one collapses a shape that reads as noise inline ──

def apply(obj, patch: BaseModel) -> None:
    """Apply every field the caller actually sent (PATCH semantics) onto obj."""
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


def matches(term: str, *columns):
    """OR-combined case-insensitive substring match across columns."""
    return or_(*(column.ilike(f"%{term}%") for column in columns))


async def count_of(session: AsyncSession, stmt) -> int:
    """Total rows a (possibly filtered) SELECT would return, ignoring its own limit/offset."""
    return await session.scalar(select(func.count()).select_from(stmt.subquery()))


def require_project(*roles: str):
    """Dependency factory: resolves the {project_id} path param to a
    Project (members eager-loaded), 404 if missing, 403 unless the
    caller holds one of `roles` on it. Use as a route parameter —
    the signature then IS the precondition, no need to read the body.
    """

    async def _dep(
        project_id: int,
        session: AsyncSession = mango.Depends(db.get_db),
        user: User = mango.Depends(auth.current_user()),
    ) -> Project:
        project = await session.scalar(
            select(Project).options(selectinload(Project.members)).where(Project.id == project_id)
        )
        if not project:
            raise mango.NotFoundError("Project not found")
        if not any(m.user_id == user.id and m.role in roles for m in project.members):
            raise mango.ForbiddenError("forbidden")
        return project

    return _dep


# ── routes — bodies now hold only what each one actually decides ──

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
        stmt = stmt.where(matches(search, Project.name, Project.description))

    total = await count_of(session, stmt)
    page_stmt = stmt.order_by(Project.created_at.desc()).offset((page - 1) * limit).limit(limit)
    rows = (await session.scalars(page_stmt)).all()
    return PaginatedProjects(total=total, page=page, limit=limit, items=rows)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    data: ProjectUpdate,
    project: Project = mango.Depends(require_project("owner", "admin")),
    session: AsyncSession = mango.Depends(db.get_db),
) -> Project:
    apply(project, data)
    project.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(
    project: Project = mango.Depends(require_project("owner")),
    session: AsyncSession = mango.Depends(db.get_db),
) -> dict:
    await session.delete(project)
    await session.commit()
    return {"message": "Project deleted successfully"}
