"""One error shape for the whole API:

    {"error": {"code": "NOT_FOUND", "message": "Company 5 not found", "details": {...}}}

- ApiError: raised by our endpoints (we choose status, code, message).
- FastAPI's own errors (unknown route -> 404, bad input -> 422) are converted to the same shape.
- Unexpected crashes are caught by the request middleware in main.py (500 INTERNAL_ERROR).
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def not_found(what: str, id_) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} {id_} not found")


HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
              405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 413: "PAYLOAD_TOO_LARGE"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        # One entry per bad field: where it is ("body.website") and what is wrong.
        fields = [{"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in exc.errors()]
        return JSONResponse(status_code=422, content=error_body(
            "VALIDATION_ERROR", "Some fields are missing or invalid.", {"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))
