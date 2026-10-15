from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUserDep,
    OwnerAccessDep,
    SessionDep,
    WorkspaceAccessDep,
    verify_csrf,
)
from app.schemas.workspace import MemberOut, WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.services import workspaces as workspace_service

# CSRF is checked first on every state-changing route in this router.
router = APIRouter(prefix="/workspaces", tags=["workspaces"], dependencies=[Depends(verify_csrf)])


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate, user: CurrentUserDep, session: SessionDep
) -> WorkspaceOut:
    workspace = await workspace_service.create_workspace(
        session, owner_id=user.id, name=payload.name
    )
    created = WorkspaceOut.model_validate(workspace)
    await session.commit()
    return created


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def read_workspace(access: WorkspaceAccessDep, session: SessionDep) -> WorkspaceOut:
    workspace = await workspace_service.get_workspace(session, access.workspace_id)
    return WorkspaceOut.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    payload: WorkspaceUpdate, access: OwnerAccessDep, session: SessionDep
) -> WorkspaceOut:
    workspace = await workspace_service.update_workspace(
        session, access.workspace_id, changes=payload.model_dump(exclude_unset=True)
    )
    updated = WorkspaceOut.model_validate(workspace)
    await session.commit()
    return updated


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(access: WorkspaceAccessDep, session: SessionDep) -> list[MemberOut]:
    members = await workspace_service.list_members(session, workspace_id=access.workspace_id)
    return [
        MemberOut(
            user_id=member.user_id,
            email=member.email,
            role=member.role,
            joined_at=member.joined_at,
        )
        for member in members
    ]
