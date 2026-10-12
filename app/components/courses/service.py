from datetime import UTC, datetime

from sqlalchemy import func, select

from app.components.courses.models import Course
from app.components.courses.schemas import CourseResponse
from app.libs.errors import ApiError
from app.libs.pagination import PAGE_SIZE, page_response


def response(course):
    return CourseResponse(
        id=course.id,
        title=course.title,
        archivedAt=course.archived_at,
        createdAt=course.created_at,
        updatedAt=course.updated_at,
    )


def list_courses(session, owner_id, page, *, archived=False):
    query = select(Course).where(
        Course.owner_id == owner_id,
        Course.archived_at.is_not(None) if archived else Course.archived_at.is_(None),
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    courses = session.scalars(
        query.order_by(Course.created_at.desc(), Course.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    return page_response([response(course) for course in courses], total, page)


def create_course(session, owner_id, data):
    course = Course(owner_id=owner_id, title=data.title)
    session.add(course)
    session.commit()
    return response(course)


def owned_course(session, owner_id, course_id, *, active=False):
    query = (
        select(Course).where(Course.id == course_id, Course.owner_id == owner_id).with_for_update()
    )
    if active:
        query = query.where(Course.archived_at.is_(None))
    course = session.scalars(query).first()
    if course is None:
        raise ApiError(404)
    return course


def rename_course(session, owner_id, course_id, data):
    course = owned_course(session, owner_id, course_id, active=True)
    course.title = data.title
    course.updated_at = datetime.now(UTC)
    session.commit()
    return response(course)


def archive_course(session, owner_id, course_id):
    course = owned_course(session, owner_id, course_id)
    if course.archived_at is None:
        course.archived_at = datetime.now(UTC)
        course.updated_at = datetime.now(UTC)
    session.commit()
    return response(course)
