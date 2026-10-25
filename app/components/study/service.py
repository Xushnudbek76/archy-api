from datetime import UTC

from sqlalchemy import select

from app.components.accounts.models import now
from app.components.documents.service import owned_document
from app.components.documents.sources import document_sources, source_revision
from app.components.study.generation import validate_content
from app.components.study.models import StudyNote
from app.components.study.schemas import NotesContent
from app.libs.errors import ApiError


def prepare(session, owner_id, document_id):
    document = owned_document(session, owner_id, document_id)
    sources = document_sources(session, owner_id, document_id)
    if not sources:
        raise ApiError(
            409,
            "study_sources_unavailable",
            "Upload readable material or finish transcription first.",
        )
    return document.title, sources, source_revision(sources)


def note_response(note):
    return {
        "available": True,
        "language": note.language,
        "provider": note.provider,
        "sourceRevision": note.source_revision,
        "createdAt": note.created_at.astimezone(UTC),
        **note.content,
    }


def read_notes(session, owner_id, document_id):
    owned_document(session, owner_id, document_id)
    note = session.scalar(select(StudyNote).where(StudyNote.document_id == document_id))
    if note is None or note.source_revision != source_revision(
        document_sources(session, owner_id, document_id)
    ):
        return {"available": False}
    return note_response(note)


def save_notes(session, owner_id, document_id, revision, language, provider, content):
    owned_document(session, owner_id, document_id, locked=True)
    sources = document_sources(session, owner_id, document_id)
    if source_revision(sources) != revision:
        raise ApiError(
            409, "source_changed", "The document changed during generation. Generate again."
        )
    content = validate_content(content, NotesContent, sources)
    note = session.get(StudyNote, document_id)
    if note is None:
        note = StudyNote(document_id=document_id)
        session.add(note)
    note.source_revision, note.language, note.provider = revision, language, provider
    note.content, note.created_at = content, now()
    session.commit()
    return note_response(note)
