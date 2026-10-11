from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from phi_protect.domain.models import Decision
from phi_protect.usecases.errors import UnverifiableFileError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI's default response echoes the submitted input, which may be PHI.
        details = [{"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(UnverifiableFileError)
    async def unverifiable_file(_: Request, error: UnverifiableFileError) -> JSONResponse:
        content = {"decision": Decision.CANNOT_VERIFY.value, "reason": str(error)}
        return JSONResponse(status_code=422, content=content)
