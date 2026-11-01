import hashlib
import json

from app.components.academics.models import ImportBatch
from app.components.academics.service import lock_owner, timetable_for
from app.components.courses.models import Course
from app.components.courses.service import replace_slots
from app.libs.errors import ApiError


def confirm_import(session, owner_id, data):
    lock_owner(session, owner_id)
    timetable_for(session, owner_id, data.timetableId, writable=True)
    canonical = data.model_dump(mode="json", exclude={"requestId"})
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    batch = session.get(ImportBatch, data.requestId)
    if batch:
        if batch.owner_id != owner_id:
            raise ApiError(404)
        if batch.digest != digest:
            raise ApiError(
                409,
                "import_conflict",
                "This import was already saved with different courses. Preview a new import.",
            )
        return {"courseIds": batch.course_ids}
    ids = []
    for item in data.courses:
        if item.timetableId not in {None, data.timetableId}:
            raise ApiError(400)
        course = Course(
            owner_id=owner_id,
            title=item.title,
            professor=item.professor,
            color=item.color,
            timetable_id=data.timetableId,
        )
        session.add(course)
        session.flush()
        replace_slots(session, course, item.schedules)
        ids.append(str(course.id))
    session.add(
        ImportBatch(
            id=data.requestId,
            owner_id=owner_id,
            timetable_id=data.timetableId,
            digest=digest,
            course_ids=ids,
        )
    )
    session.commit()
    return {"courseIds": ids}
