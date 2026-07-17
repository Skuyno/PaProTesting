"""Application entry point."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import OperationAlreadyExistsError
from app.router import router

app = FastAPI()
app.include_router(router)


@app.exception_handler(OperationAlreadyExistsError)
async def operation_conflict_handler(
    request: Request, exc: OperationAlreadyExistsError
) -> JSONResponse:
    """Map duplicate operation creation to 409 Conflict."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})
