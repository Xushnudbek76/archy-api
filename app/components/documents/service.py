from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.components.accounts.models import now
from app.components.courses.models import Course
from app.components.documents.models import Document
from app.components.documents.schemas import DocumentDetail, DocumentPage, DocumentResponse
from app.components.recordings.models import Recording
from app.libs.errors import ApiError
from app.libs.pagination import PAGE_SIZE, page_response


def document_response(document, *, detail=False):
    data = dict(
        id=document.id,
        title=document.title,
        courseId=document.course_id,
        recordingId=document.recording_id,
        hasPdf=document.pdf_size_bytes is not None,
        fileName=document.file_name,
        pdfSizeBytes=document.pdf_size_bytes,
        pageCount=document.page_count,
        archivedAt=document.archived_at,
        createdAt=document.created_at,
        updatedAt=document.updated_at,
    )
    return DocumentDetail(**data, text=document.text) if detail else DocumentResponse(**data)


def references(session, owner_id, course_id, recording_id):
    if course_id is not None:
        course = session.scalars(
            select(Course).where(
                Course.id == course_id, Course.owner_id == owner_id, Course.archived_at.is_(None)
            )
        ).first()
        if course is None:
            raise ApiError(404)
    if recording_id is not None:
        recording = session.scalars(
            select(Recording)
            .join(Course, Course.id == Recording.course_id)
            .where(Recording.id == recording_id, Course.owner_id == owner_id)
        ).first()
        if recording is None:
            raise ApiError(404)


def materialize_recording(session, recording):
    owner_id = session.scalar(select(Course.owner_id).where(Course.id == recording.course_id))
    session.execute(
        insert(Document)
        .values(
            id=recording.id,
            owner_id=owner_id,
            title=recording.title,
            course_id=recording.course_id,
            recording_id=recording.id,
            created_at=recording.created_at,
            updated_at=recording.created_at,
        )
        .on_conflict_do_nothing(index_elements=[Document.id])
    )


def owned_document(session, owner_id, key, *, locked=False, archived=False):
    query = select(Document).where(Document.id == key, Document.owner_id == owner_id)
    if not archived:
        query = query.where(Document.archived_at.is_(None))
    if locked:
        query = query.with_for_update()
    document = session.scalars(query).first()
    if document is None:
        raise ApiError(404)
    return document


def create_document(session, owner_id, data):
    references(session, owner_id, data.courseId, data.recordingId)
    document = Document(
        owner_id=owner_id, title=data.title, course_id=data.courseId, recording_id=data.recordingId
    )
    session.add(document)
    session.commit()
    return document_response(document)


def read_document(session, owner_id, key):
    return document_response(owned_document(session, owner_id, key), detail=True)


def list_documents(session, owner_id, page, q="", course_id=None):
    query = select(Document).where(Document.owner_id == owner_id, Document.archived_at.is_(None))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Document.title.ilike(f"%{escaped}%", escape="\\"))
    if course_id is not None:
        query = query.where(Document.course_id == course_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    result = page_response([document_response(row) for row in rows], total, page)
    return DocumentPage(
        **result, page=page, pageSize=PAGE_SIZE, previousPage=page - 1 if page > 1 else None
    )


def update_document(session, owner_id, key, data):
    document = owned_document(session, owner_id, key, locked=True)
    fields = data.model_fields_set
    references(
        session,
        owner_id,
        data.courseId if "courseId" in fields else None,
        data.recordingId if "recordingId" in fields else None,
    )
    for field, attribute in (
        ("title", "title"),
        ("courseId", "course_id"),
        ("recordingId", "recording_id"),
    ):
        if field in fields:
            setattr(document, attribute, getattr(data, field))
    document.updated_at = now()
    session.commit()
    return document_response(document)


def archive_document(session, owner_id, key):
    document = owned_document(session, owner_id, key, locked=True, archived=True)
    if document.archived_at is None:
        document.archived_at = now()
        document.updated_at = document.archived_at
        session.commit()
    return document_response(document)


def authorize_upload(session, owner_id, key):
    document = owned_document(session, owner_id, key)
    if document.pdf_size_bytes is not None:
        raise ApiError(409, "pdf_exists", "This document already has a PDF.")
    return document_response(document)


def save_pdf(session, owner_id, key, body, file_name, storage_root):
    from app.components.documents.storage import DocumentStorage

    document = owned_document(session, owner_id, key, locked=True)
    if document.pdf_size_bytes is not None:
        raise ApiError(409, "pdf_exists", "This document already has a PDF.")
    try:
        with DocumentStorage(storage_root) as storage:
            try:
                storage.publish(key, body)
            except FileExistsError:
                raise ApiError(409, "pdf_exists", "This document already has a PDF.") from None
            try:
                document.file_name = file_name
                document.pdf_size_bytes = len(body)
                document.updated_at = now()
                session.commit()
            except BaseException:
                storage.remove(key)
                raise
    except OSError:
        raise ApiError(
            503, "storage_unavailable", "PDF storage is temporarily unavailable."
        ) from None
    return document_response(document, detail=True)


def authorize_pdf(session, owner_id, key, storage_root):
    from app.components.documents.storage import DocumentStorage

    document = owned_document(session, owner_id, key)
    if document.pdf_size_bytes is None:
        raise ApiError(404)
    try:
        with DocumentStorage(storage_root) as storage:
            import os

            os.close(storage.open(key, document.pdf_size_bytes))
    except OSError:
        raise ApiError(
            503, "storage_unavailable", "PDF storage is temporarily unavailable."
        ) from None
    return storage_root, key, document.pdf_size_bytes, document.file_name
