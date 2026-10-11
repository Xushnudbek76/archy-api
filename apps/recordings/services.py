from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from apps.core.errors import ClientError
from apps.courses.models import Course
from apps.recordings.media import InvalidAudio, inspect_audio
from apps.recordings.models import Recording, Upload
from apps.recordings.storage import LocalRecordingStorage, StorageConflict

CHUNK_BYTES = 4 * 1024 * 1024
ERRORS = {
    "invalid_audio": "This file is not supported audio. Use MP3, M4A, WAV, FLAC, Ogg or WebM.",
    "checksum_mismatch": "The file changed during upload. Please select it and start again.",
}


def storage():
    return LocalRecordingStorage(settings.RECORDING_STORAGE_ROOT)


def conflict():
    return ClientError(409, "upload_conflict", "Refresh the upload status before continuing.")


def unavailable():
    return ClientError(503, "storage_unavailable", "Recording storage is temporarily unavailable.")


def owned_upload(owner, key, locked=False):
    query = Upload.objects.select_related("course", "recording")
    if locked:
        query = query.select_for_update(of=("self",))
    return get_object_or_404(query, pk=key, course__owner=owner)


@transaction.atomic
def admit_upload(owner, data):
    existing = Upload.objects.select_for_update().filter(pk=data["id"]).first()
    if existing is None:
        course = get_object_or_404(
            Course, pk=data["courseId"], owner=owner, archived_at__isnull=True
        )
        try:
            if storage().available_bytes() < data["sizeBytes"] * 2:
                raise ClientError(
                    507, "storage_full", "There is not enough server storage for this file."
                )
            with transaction.atomic():
                upload = Upload.objects.create(
                    id=data["id"],
                    course=course,
                    title=data["title"],
                    file_name=data["fileName"],
                    size_bytes=data["sizeBytes"],
                    sha256=data["sha256"],
                )
            return upload, True
        except OSError:
            raise unavailable() from None
        except IntegrityError:
            existing = owned_upload(owner, data["id"], locked=True)
    if existing.course.owner_id != owner.id:
        get_object_or_404(Upload, pk=data["id"], course__owner=owner)
    expected = (
        data["courseId"],
        data["title"],
        data["fileName"],
        data["sizeBytes"],
        data["sha256"],
    )
    actual = (
        existing.course_id,
        existing.title,
        existing.file_name,
        existing.size_bytes,
        existing.sha256,
    )
    if expected != actual:
        raise conflict()
    return existing, False


@transaction.atomic
def receive_chunk(owner, key, offset, data):
    upload = owned_upload(owner, key, locked=True)
    if upload.status != Upload.Status.UPLOADING or offset > upload.uploaded_bytes:
        raise conflict()
    if not data or len(data) > CHUNK_BYTES:
        raise ClientError(
            413 if len(data) > CHUNK_BYTES else 400,
            "invalid_chunk",
            "Upload a nonempty chunk of at most 4 MiB.",
        )
    if offset + len(data) > upload.size_bytes:
        raise ClientError(400, "invalid_chunk", "The chunk exceeds the declared file size.")
    try:
        if offset < upload.uploaded_bytes:
            part = storage().upload_directory(key) / f"{offset}.part"
            if not part.is_file() or part.read_bytes() != data:
                raise conflict()
            return upload
        storage().write_part(key, offset, data)
    except StorageConflict:
        raise conflict() from None
    except OSError:
        raise unavailable() from None
    upload.uploaded_bytes += len(data)
    upload.save(update_fields=["uploaded_bytes", "updated_at"])
    return upload


@transaction.atomic
def complete_upload(owner, key):
    upload = owned_upload(owner, key, locked=True)
    if upload.status in {Upload.Status.ACCEPTED, Upload.Status.FAILED}:
        return upload
    if upload.status != Upload.Status.UPLOADING or upload.uploaded_bytes != upload.size_bytes:
        raise conflict()
    disk = storage()
    try:
        path, checksum, size = disk.assemble(key)
        if size != upload.size_bytes or checksum != upload.sha256:
            upload.error_code = "checksum_mismatch"
        else:
            try:
                media = inspect_audio(path)
            except InvalidAudio:
                upload.error_code = "invalid_audio"
        if upload.error_code:
            upload.status = Upload.Status.FAILED
        else:
            disk.publish(upload.id, path)
            Recording.objects.create(
                id=upload.id,
                upload=upload,
                course=upload.course,
                title=upload.title,
                size_bytes=size,
                sha256=checksum,
                **media,
            )
            upload.status = Upload.Status.ACCEPTED
        upload.save(update_fields=["status", "error_code", "updated_at"])
        transaction.on_commit(lambda: disk.remove_upload(key))
    except (OSError, StorageConflict):
        raise unavailable() from None
    return owned_upload(owner, key)


@transaction.atomic
def cancel_upload(owner, key):
    upload = owned_upload(owner, key, locked=True)
    if upload.status == Upload.Status.ACCEPTED:
        raise conflict()
    if upload.status != Upload.Status.CANCELLED:
        upload.status = Upload.Status.CANCELLED
        upload.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: storage().remove_upload(key))
    return upload
