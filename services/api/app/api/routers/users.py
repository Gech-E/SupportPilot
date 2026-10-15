from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.auth import UserOut
from app.schemas.workspace import MeOut, WorkspaceSummary
from app.services import workspaces as workspace_service

router = APIRouter(tags=["users"])


@router.get("/me", response_model=MeOut)
async def read_me(user: CurrentUserDep, session: SessionDep) -> MeOut:
    """The signed-in user and the workspaces they belong to."""
    memberships = await workspace_service.list_workspaces_for_user(session, user_id=user.id)
    return MeOut(
        user=UserOut(id=user.id, email=user.email),
        workspaces=[
            WorkspaceSummary(id=item.workspace_id, name=item.name, role=item.role)
            for item in memberships
        ],
    )
