"""Domain errors.

Services raise these; the HTTP layer turns them into a single, consistent error shape
(see ``app/api/error_handlers.py``). Messages are written for end users: never include SQL,
stack traces, secrets, or other tenants' identifiers.
"""


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Something went wrong."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)
        if code is not None:
            self.code = code


class UnauthenticatedError(AppError):
    status_code = 401
    code = "unauthenticated"
    default_message = "Authentication is required."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to do this."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many attempts. Try again later."

    def __init__(self, *, retry_after: int, message: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    default_message = "The service is temporarily unavailable."
