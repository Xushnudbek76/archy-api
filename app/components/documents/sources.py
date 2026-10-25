import hashlib
import json

from sqlalchemy import select

from app.components.documents.service import owned_document
from app.components.processing.models import Job, Transcript


def document_sources(session, owner_id, document_id):
    document = owned_document(session, owner_id, document_id)
    items = []

    def add(kind, text, page=None, start=None, end=None):
        if not text.strip():
            return
        value = dict(kind=kind, text=text, page=page, start=start, end=end)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        value["id"] = kind + ":" + hashlib.sha256(encoded).hexdigest()[:24]
        items.append(value)

    if document.pages is not None:
        for index, text in enumerate(document.pages):
            add("pdf", text, page=index + 1)
    elif document.text:
        add("pdf", document.text)
    if document.recording_id:
        transcript = session.scalar(
            select(Transcript).join(Job).where(Job.recording_id == document.recording_id)
        )
        if transcript:
            if transcript.segments:
                for segment in transcript.segments:
                    add("transcript", segment["text"], start=segment["start"], end=segment["end"])
            else:
                add("transcript", transcript.text)
    return items


def source_revision(items):
    return hashlib.sha256(
        json.dumps(items, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
