from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep
from app.core.errors import ServiceUnavailableError

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthOut)
async def liveness() -> HealthOut:
    """The process is up. Does not touch dependencies, so it never flaps with the database."""
    return HealthOut(status="ok")


@router.get("/ready", response_model=HealthOut)
async def readiness(session: SessionDep) -> HealthOut:
    """The process can serve traffic: the database answers."""
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise ServiceUnavailableError("The database is not reachable.", code="not_ready") from exc
    return HealthOut(status="ok")
