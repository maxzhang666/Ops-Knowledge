from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, id: str | None = None):
        msg = f"{resource} not found" if id is None else f"{resource} with id '{id}' not found"
        super().__init__(msg, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=409)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class QuotaExceededError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=429)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )
