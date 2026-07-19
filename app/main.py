"""Application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import OperationAlreadyExistsError, OperationNotFoundError
from app.provider import ProviderClient
from app.router import router
from app.worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the provider client and worker; stop them cleanly on shutdown."""
    provider = ProviderClient()
    stop = asyncio.Event()
    worker_task = asyncio.create_task(run_worker(provider, stop))
    yield
    stop.set()
    await worker_task
    await provider.aclose()


app = FastAPI(lifespan=lifespan)
app.include_router(router)


@app.exception_handler(OperationAlreadyExistsError)
async def operation_conflict_handler(
    request: Request, exc: OperationAlreadyExistsError
) -> JSONResponse:
    """Map duplicate operation creation to 409 Conflict."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(OperationNotFoundError)
async def operation_not_found_handler(
    request: Request, exc: OperationNotFoundError
) -> JSONResponse:
    """Map missing operations to 404 not found."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})
