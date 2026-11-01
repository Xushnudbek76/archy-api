from datetime import UTC, datetime

from sqlalchemy import delete, func, select

from app.components.academics.models import AcademicTerm, CourseSchedule, Timetable
from app.components.academics.service import lock_owner, timetable_for
from app.components.courses.models import Course
from app.components.courses.schemas import CourseDetailResponse
from app.libs.errors import ApiError
from app.libs.pagination import PAGE_SIZE, page_response


def response(course, slots=(), *, read_only=False):
    return CourseDetailResponse(
        id=course.id,
        title=course.title,
        archivedAt=course.archived_at,
        createdAt=course.created_at,
        updatedAt=course.updated_at,
        professor=course.professor,
        color=course.color,
        timetableId=course.timetable_id,
        readOnly=read_only or course.archived_at is not None,
        schedules=[
            {
                "days": slot.days,
                "startTime": slot.start_time,
                "endTime": slot.end_time,
                "room": slot.room,
            }
            for slot in slots
        ],
    )


def slots_for(session, course_id):
    return session.scalars(
        select(CourseSchedule)
        .where(CourseSchedule.course_id == course_id)
        .order_by(CourseSchedule.position)
    ).all()


def is_read_only(session, course):
    if course.archived_at is not None:
        return True
    if course.timetable_id is None:
        return False
    return (
        session.scalar(
            select(AcademicTerm.archived_at)
            .join(Timetable, Timetable.term_id == AcademicTerm.id)
            .where(Timetable.id == course.timetable_id)
        )
        is not None
    )


def ensure_writable(session, owner_id, course):
    if course.timetable_id is not None:
        timetable_for(session, owner_id, course.timetable_id, writable=True)


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
    slots = (
        session.scalars(
            select(CourseSchedule)
            .where(CourseSchedule.course_id.in_([course.id for course in courses]))
            .order_by(CourseSchedule.position)
        ).all()
        if courses
        else []
    )
    archived_tables = set(
        session.scalars(
            select(Timetable.id)
            .join(AcademicTerm, Timetable.term_id == AcademicTerm.id)
            .where(Timetable.owner_id == owner_id, AcademicTerm.archived_at.is_not(None))
        ).all()
    )
    return page_response(
        [
            response(
                course,
                [slot for slot in slots if slot.course_id == course.id],
                read_only=course.timetable_id in archived_tables,
            )
            for course in courses
        ],
        total,
        page,
    )


def replace_slots(session, course, slots):
    session.execute(delete(CourseSchedule).where(CourseSchedule.course_id == course.id))
    for position, slot in enumerate(slots):
        session.add(
            CourseSchedule(
                course_id=course.id,
                position=position,
                days=slot.days,
                start_time=slot.startTime,
                end_time=slot.endTime,
                room=slot.room,
            )
        )


def create_course(session, owner_id, data):
    lock_owner(session, owner_id)
    if data.timetableId is not None:
        timetable_for(session, owner_id, data.timetableId, writable=True)
    course = Course(
        owner_id=owner_id,
        title=data.title,
        professor=data.professor,
        color=data.color,
        timetable_id=data.timetableId,
    )
    session.add(course)
    session.flush()
    replace_slots(session, course, data.schedules)
    session.commit()
    return response(course, slots_for(session, course.id))


def owned_course(session, owner_id, course_id, *, active=False):
    if active:
        lock_owner(session, owner_id)
    query = (
        select(Course).where(Course.id == course_id, Course.owner_id == owner_id).with_for_update()
    )
    if active:
        query = query.where(Course.archived_at.is_(None))
    course = session.scalars(query).first()
    if course is None:
        raise ApiError(404)
    if active:
        ensure_writable(session, owner_id, course)
    return course


def rename_course(session, owner_id, course_id, data):
    course = owned_course(session, owner_id, course_id, active=True)
    if "timetableId" in data.model_fields_set and data.timetableId is not None:
        timetable_for(session, owner_id, data.timetableId, writable=True)
    for field, attribute in [
        ("title", "title"),
        ("professor", "professor"),
        ("color", "color"),
        ("timetableId", "timetable_id"),
    ]:
        if field in data.model_fields_set:
            setattr(course, attribute, getattr(data, field))
    if "schedules" in data.model_fields_set:
        replace_slots(session, course, data.schedules)
    course.updated_at = datetime.now(UTC)
    session.commit()
    return response(course, slots_for(session, course.id))


def archive_course(session, owner_id, course_id):
    lock_owner(session, owner_id)
    course = owned_course(session, owner_id, course_id)
    ensure_writable(session, owner_id, course)
    if course.archived_at is None:
        course.archived_at = datetime.now(UTC)
        course.updated_at = datetime.now(UTC)
    session.commit()
    return response(course, slots_for(session, course.id), read_only=True)
