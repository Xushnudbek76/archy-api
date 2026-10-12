from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.components.accounts.schemas import StrictInput
from app.components.courses import service
from app.components.courses.schemas import CourseInput
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.pagination import page_query

router = APIRouter(prefix="/v1/courses", dependencies=[Depends(ensure_csrf)])


@router.get("")
def courses(request: Request, identity: IdentityDep, session: SessionDep):
    page = page_query(request.query_params, archived=True)
    return service.list_courses(
        session, identity.id, page, archived=request.query_params.get("archived") == "true"
    )


@router.post("", status_code=201)
def create(data: CourseInput, identity: IdentityDep, session: SessionDep):
    return service.create_course(session, identity.id, data)


@router.patch("/{course_id}")
def rename(course_id: UUID, data: CourseInput, identity: IdentityDep, session: SessionDep):
    return service.rename_course(session, identity.id, course_id, data)


@router.post("/{course_id}/archive")
def archive(course_id: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.archive_course(session, identity.id, course_id)
