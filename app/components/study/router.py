from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request

from app.components.documents.router import owned_unit
from app.components.study import generation, service
from app.components.study.schemas import AttemptInput, NotesInput, QuizInput, RetryInput
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.workers import run_worker

router = APIRouter(dependencies=[Depends(ensure_csrf)])


@router.get("/v1/documents/{document_id}/study-notes")
def notes(document_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_notes(session, identity.id, document_id)


@router.post("/v1/documents/{document_id}/study-notes")
async def create_notes(document_id: UUID, data: NotesInput, request: Request):
    _, sources, revision = await run_worker(owned_unit, request, service.prepare, document_id)
    limiter = request.app.state.study_limiter
    try:
        limiter.acquire_nowait()
    except anyio.WouldBlock:
        raise ApiError(429, retry_after=5) from None
    try:
        config = request.app.state.settings.processing
        content = await run_worker(generation.generate_notes, sources, data.language, config)
        return await run_worker(
            owned_unit,
            request,
            service.save_notes,
            document_id,
            revision,
            data.language,
            config.backend,
            content,
        )
    finally:
        limiter.release()


@router.get("/v1/documents/{document_id}/quizzes")
def quizzes(document_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.list_quizzes(session, identity.id, document_id)


@router.get("/v1/quizzes/{quiz_id}")
def quiz(quiz_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_quiz(session, identity.id, quiz_id)


@router.post("/v1/documents/{document_id}/quizzes", status_code=201)
async def create_quiz(document_id: UUID, data: QuizInput, request: Request):
    _, sources, revision = await run_worker(owned_unit, request, service.prepare, document_id)
    limiter = request.app.state.study_limiter
    try:
        limiter.acquire_nowait()
    except anyio.WouldBlock:
        raise ApiError(429, retry_after=5) from None
    try:
        config = request.app.state.settings.processing
        content = await run_worker(generation.generate_quiz, sources, data, config)
        return await run_worker(
            owned_unit,
            request,
            service.save_quiz,
            document_id,
            revision,
            data,
            config.backend,
            content,
        )
    finally:
        limiter.release()


@router.get("/v1/quizzes/{quiz_id}/attempts")
def attempts(quiz_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.list_attempts(session, identity.id, quiz_id)


@router.post("/v1/quizzes/{quiz_id}/attempts", status_code=201)
def create_attempt(quiz_id: UUID, data: AttemptInput, identity: IdentityDep, session: SessionDep):
    return service.save_attempt(session, identity.id, quiz_id, data)


@router.post("/v1/quizzes/{quiz_id}/retry", status_code=201)
def retry(quiz_id: UUID, data: RetryInput, identity: IdentityDep, session: SessionDep):
    return service.retry_quiz(session, identity.id, quiz_id, data.attemptId)
