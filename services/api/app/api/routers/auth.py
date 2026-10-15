from fastapi import APIRouter, Depends, Request, Response

from app.api.cookies import end_session, start_session
from app.api.deps import LimitersDep, SessionDep, SettingsDep, verify_csrf
from app.schemas.auth import LoginRequest, SignupRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # The socket peer. Behind a reverse proxy, trust forwarded headers only from known proxies.
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    limiters: LimitersDep,
) -> UserOut:
    limiters.ip.check(_client_ip(request))
    user = await auth_service.register_user(
        session, email=payload.email, password=payload.password.get_secret_value()
    )
    created = UserOut.model_validate(user)
    await session.commit()
    start_session(response, created.id, settings)
    return created


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    limiters: LimitersDep,
) -> UserOut:
    client_ip = _client_ip(request)
    limiters.ip.check(client_ip)
    limiters.login.check(f"{client_ip}|{payload.email}")
    user = await auth_service.authenticate(
        session, email=payload.email, password=payload.password.get_secret_value()
    )
    start_session(response, user.id, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204, dependencies=[Depends(verify_csrf)])
async def logout(response: Response, settings: SettingsDep) -> None:
    end_session(response, settings)
