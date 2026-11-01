import os
from contextlib import asynccontextmanager

import anyio
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.database.base import Base
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings
from app.libs.errors import ApiError, error_response
from app.libs.logging import configure_logging
from app.libs.middleware import RequestMiddleware


def create_app(settings):
    engine = create_engine_for(settings)

    @asynccontextmanager
    async def lifespan(application):
        anyio.to_thread.current_default_thread_limiter().total_tokens = 40
        yield
        engine.dispose()

    application = FastAPI(title="Archy API", redirect_slashes=False, lifespan=lifespan)
    from app.components.academics.router import router as academics_router
    from app.components.accounts.router import router as accounts_router
    from app.components.courses.router import router as courses_router
    from app.components.demo.router import router as demo_router
    from app.components.documents.router import router as documents_router
    from app.components.processing.router import router as processing_router
    from app.components.recordings.router import router as recordings_router
    from app.components.study.router import router as study_router
    from app.components.tutor.router import router as tutor_router
    from app.libs.throttling import AccountLimiter

    application.include_router(demo_router)
    application.include_router(tutor_router)
    application.include_router(study_router)
    application.state.study_limiter = anyio.CapacityLimiter(2)
    application.include_router(documents_router)
    application.include_router(processing_router)
    application.include_router(recordings_router)
    application.state.chunk_limiter = anyio.CapacityLimiter(4)
    application.state.pdf_limiter = anyio.CapacityLimiter(2)
    application.include_router(accounts_router)
    application.include_router(academics_router)
    application.state.timetable_import_limiter = anyio.CapacityLimiter(2)
    application.include_router(courses_router)
    application.state.outbox = []
    application.state.account_limiter = AccountLimiter()
    application.state.settings = settings
    application.state.engine = engine
    application.state.sessions = session_factory(engine)
    application.add_middleware(RequestMiddleware, allowed_hosts=settings.allowed_hosts)
    configure_logging()

    @application.exception_handler(ApiError)
    async def domain_error(request, error):
        return error_response(error, request.state.request_id)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return error_response(ApiError(400), request.state.request_id)

    @application.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response(ApiError(error.status_code), request.state.request_id)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return error_response(ApiError(503), request.state.request_id)

    @application.get("/v1/health/live")
    async def live():
        return {"status": "ok"}

    @application.get("/v1/health/ready")
    def ready():
        with engine.connect() as connection:
            for table in Base.metadata.sorted_tables:
                connection.execute(select(table).limit(0))
        return {"status": "ok"}

    return application


def build_app():
    return create_app(load_settings({**dotenv_values(".env"), **os.environ}))
