from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.components.academics.service import lock_owner
from app.components.accounts.models import now
from app.components.courses.models import Course
from app.components.courses.service import ensure_writable
from app.components.documents.models import Document
from app.components.recordings.media import InvalidAudio, inspect_audio
from app.components.recordings.models import Recording, Upload
from app.components.recordings.schemas import RecordingResponse, UploadResponse
from app.components.recordings.storage import LocalRecordingStorage, StorageConflict
from app.libs.errors import ApiError
from app.libs.pagination import PAGE_SIZE, page_response

CHUNK_BYTES = 4 * 1024 * 1024
ERRORS = {
    "invalid_audio": "This file is not supported audio. Use MP3, M4A, WAV, FLAC, Ogg or WebM.",
    "checksum_mismatch": "The file changed during upload. Please select it and start again.",
    "audio_too_long": (
        "This audio exceeds its upload duration limit. Choose a shorter file and "
        "start a new upload."
    ),
    "duration_unavailable": (
        "The audio duration could not be verified. Export the file again and start a new upload."
    ),
}


def conflict():
    return ApiError(409, "upload_conflict", "Refresh the upload status before continuing.")


def unavailable():
    return ApiError(503, "storage_unavailable", "Recording storage is temporarily unavailable.")


def recording_response(recording, course, document_id=None):
    return RecordingResponse(
        id=recording.id,
        courseId=course.id,
        courseTitle=course.title,
        title=recording.title,
        sizeBytes=recording.size_bytes,
        durationSeconds=recording.duration_seconds,
        contentType=recording.content_type,
        createdAt=recording.created_at,
        documentId=document_id,
    )


def upload_response(session, upload):
    course = session.get(Course, upload.course_id)
    recording = session.scalars(select(Recording).where(Recording.upload_id == upload.id)).first()
    return UploadResponse(
        id=upload.id,
        courseId=course.id,
        courseTitle=course.title,
        title=upload.title,
        fileName=upload.file_name,
        sizeBytes=upload.size_bytes,
        uploadedBytes=upload.uploaded_bytes,
        sha256=upload.sha256,
        status=upload.status,
        errorCode=upload.error_code,
        maxDurationSeconds=upload.max_duration_seconds,
        recording=recording_response(recording, course) if recording else None,
        createdAt=upload.created_at,
    )


def owned_upload(session, owner_id, key, *, locked=False):
    query = (
        select(Upload)
        .join(Course, Course.id == Upload.course_id)
        .where(Upload.id == key, Course.owner_id == owner_id)
    )
    if locked:
        query = query.with_for_update(of=Upload)
    upload = session.scalars(query).first()
    if upload is None:
        raise ApiError(404)
    return upload


def read_upload(session, owner_id, key):
    return upload_response(session, owned_upload(session, owner_id, key))


def admit_upload(session, owner_id, data, storage_root, max_duration_seconds=1200):
    lock_owner(session, owner_id)
    existing = session.scalars(select(Upload).where(Upload.id == data.id).with_for_update()).first()
    if existing is None:
        course = session.scalars(
            select(Course).where(
                Course.id == data.courseId,
                Course.owner_id == owner_id,
                Course.archived_at.is_(None),
            )
        ).first()
        if course is None:
            raise ApiError(404)
        ensure_writable(session, owner_id, course)
        try:
            if LocalRecordingStorage(storage_root).available_bytes() < data.sizeBytes * 2:
                raise ApiError(
                    507, "storage_full", "There is not enough server storage for this file."
                )
            with session.begin_nested():
                upload = Upload(
                    id=data.id,
                    course_id=course.id,
                    title=data.title,
                    file_name=data.fileName,
                    size_bytes=data.sizeBytes,
                    sha256=data.sha256,
                    max_duration_seconds=max_duration_seconds,
                )
                session.add(upload)
                session.flush()
            session.commit()
            return upload_response(session, upload), True
        except OSError:
            raise unavailable() from None
        except IntegrityError:
            existing = owned_upload(session, owner_id, data.id, locked=True)
    if session.get(Course, existing.course_id).owner_id != owner_id:
        raise ApiError(404)
    if (
        existing.course_id,
        existing.title,
        existing.file_name,
        existing.size_bytes,
        existing.sha256,
    ) != (data.courseId, data.title, data.fileName, data.sizeBytes, data.sha256):
        raise conflict()
    return upload_response(session, existing), False


def receive_chunk(session, owner_id, key, offset, body, storage_root):
    lock_owner(session, owner_id)
    upload = owned_upload(session, owner_id, key, locked=True)
    if upload.status != "UPLOADING" or offset > upload.uploaded_bytes:
        raise conflict()
    if not body or len(body) > CHUNK_BYTES:
        raise ApiError(
            413 if len(body) > CHUNK_BYTES else 400,
            "invalid_chunk",
            "Upload a nonempty chunk of at most 4 MiB.",
        )
    if offset + len(body) > upload.size_bytes:
        raise ApiError(400, "invalid_chunk", "The chunk exceeds the declared file size.")
    disk = LocalRecordingStorage(storage_root)
    try:
        if offset < upload.uploaded_bytes:
            part = disk.upload_directory(key) / f"{offset}.part"
            if not part.is_file() or part.read_bytes() != body:
                raise conflict()
            return upload_response(session, upload)
        disk.write_part(key, offset, body)
    except StorageConflict:
        raise conflict() from None
    except OSError:
        raise unavailable() from None
    upload.uploaded_bytes += len(body)
    upload.updated_at = now()
    session.commit()
    return upload_response(session, upload)


def complete_upload(session, owner_id, key, storage_root, processing=None):
    lock_owner(session, owner_id)
    upload = owned_upload(session, owner_id, key, locked=True)
    if upload.status in {"ACCEPTED", "FAILED"}:
        return upload_response(session, upload)
    if upload.status != "UPLOADING" or upload.uploaded_bytes != upload.size_bytes:
        raise conflict()
    disk = LocalRecordingStorage(storage_root)
    try:
        path, checksum, size = disk.assemble(key)
        if size != upload.size_bytes or checksum != upload.sha256:
            upload.error_code = "checksum_mismatch"
        else:
            try:
                media = inspect_audio(path, upload.max_duration_seconds)
            except InvalidAudio as error:
                upload.error_code = error.code
        if upload.error_code:
            upload.status = "FAILED"
        else:
            disk.publish(key, path)
            session.add(
                Recording(
                    id=key,
                    upload_id=key,
                    course_id=upload.course_id,
                    title=upload.title,
                    size_bytes=size,
                    sha256=checksum,
                    content_type=media.content_type,
                    duration_seconds=media.duration_seconds,
                )
            )
            session.flush()
            from app.components.documents.service import materialize_recording

            materialize_recording(session, session.get(Recording, key))
            from app.components.processing.service import enqueue

            enqueue(session, upload, processing)
            upload.status = "ACCEPTED"
        upload.updated_at = now()
        session.commit()
        disk.remove_upload(key)
    except (OSError, StorageConflict):
        raise unavailable() from None
    return read_upload(session, owner_id, key)


def cancel_upload(session, owner_id, key, storage_root):
    lock_owner(session, owner_id)
    upload = owned_upload(session, owner_id, key, locked=True)
    if upload.status == "ACCEPTED":
        raise conflict()
    upload.status = "CANCELLED"
    upload.updated_at = now()
    session.commit()
    LocalRecordingStorage(storage_root).remove_upload(key)
    return upload_response(session, upload)


def list_uploads(session, owner_id, page):
    query = (
        select(Upload)
        .join(Course, Course.id == Upload.course_id)
        .where(Course.owner_id == owner_id, Upload.status == "UPLOADING")
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(Upload.created_at.desc(), Upload.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    return page_response([upload_response(session, row) for row in rows], total, page)


def list_recordings(session, owner_id, page, *, q="", course_id=None):
    query = (
        select(Recording, Course)
        .join(Course, Course.id == Recording.course_id)
        .where(Course.owner_id == owner_id)
    )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Recording.title.ilike(f"%{escaped}%", escape="\\"))
    if course_id is not None:
        query = query.where(Recording.course_id == course_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(
        query.order_by(Recording.created_at.desc(), Recording.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    documents = recording_documents(session, owner_id, [recording.id for recording, _ in rows])
    return page_response(
        [
            recording_response(recording, course, documents.get(recording.id))
            for recording, course in rows
        ],
        total,
        page,
    )


def recording_documents(session, owner_id, ids):
    if not ids:
        return {}
    rows = session.execute(
        select(Document.recording_id, Document.id)
        .where(
            Document.owner_id == owner_id,
            Document.recording_id.in_(ids),
            Document.archived_at.is_(None),
        )
        .order_by(
            (Document.id != Document.recording_id).desc(),
            Document.created_at.desc(),
            Document.id.desc(),
        )
    ).all()
    result = {}
    for recording_id, document_id in rows:
        result.setdefault(recording_id, document_id)
    return result


def open_study_document(session, owner_id, key):
    from app.components.documents.service import materialize_recording

    lock_owner(session, owner_id)
    recording = session.scalar(
        select(Recording)
        .join(Course, Course.id == Recording.course_id)
        .where(Recording.id == key, Course.owner_id == owner_id)
        .with_for_update(of=Recording)
    )
    if recording is None:
        raise ApiError(404)
    existing = recording_documents(session, owner_id, [key]).get(key)
    if existing:
        return {"documentId": existing}
    course = session.get(Course, recording.course_id)
    ensure_writable(session, owner_id, course)
    materialize_recording(session, recording)
    session.commit()
    document_id = recording_documents(session, owner_id, [key]).get(key)
    if document_id is None:
        raise ApiError(409, "document_archived", "This recording’s study document is archived.")
    return {"documentId": document_id}


@dataclass(frozen=True)
class AudioFile:
    path: Path
    size: int
    content_type: str


def authorize_audio(session, owner_id, key, storage_root):
    recording = session.scalars(
        select(Recording)
        .join(Course, Course.id == Recording.course_id)
        .where(Recording.id == key, Course.owner_id == owner_id)
    ).first()
    if recording is None:
        raise ApiError(404)
    path = LocalRecordingStorage(storage_root).recording_path(key)
    try:
        if not path.is_file() or path.stat().st_size != recording.size_bytes:
            raise unavailable()
    except OSError:
        raise unavailable() from None
    return AudioFile(path, recording.size_bytes, recording.content_type)
