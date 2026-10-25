import hashlib
import json
from datetime import UTC
from uuid import uuid4

from sqlalchemy import func, select

from app.components.accounts.models import now
from app.components.documents.service import owned_document
from app.components.documents.sources import document_sources, source_revision
from app.components.study.generation import validate_content, validate_quiz
from app.components.study.models import Attempt, Quiz, StudyNote
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


def quiz_response(quiz):
    return {
        "id": quiz.id,
        "documentId": quiz.document_id,
        "title": quiz.title,
        "language": quiz.language,
        "provider": quiz.provider,
        "sourceRevision": quiz.source_revision,
        "createdAt": quiz.created_at.astimezone(UTC),
        "questions": [
            {key: question[key] for key in ("id", "type", "prompt", "options")}
            for question in quiz.questions
        ],
    }


def owned_quiz(session, owner_id, quiz_id, *, locked=False):
    query = select(Quiz).where(Quiz.id == quiz_id)
    if locked:
        query = query.with_for_update()
    quiz = session.scalar(query)
    if quiz is None:
        raise ApiError(404)
    owned_document(session, owner_id, quiz.document_id)
    return quiz


def read_quiz(session, owner_id, quiz_id):
    return quiz_response(owned_quiz(session, owner_id, quiz_id))


def list_quizzes(session, owner_id, document_id):
    owned_document(session, owner_id, document_id)
    rows = session.scalars(
        select(Quiz)
        .where(Quiz.document_id == document_id)
        .order_by(Quiz.created_at.desc(), Quiz.id.desc())
        .limit(50)
    ).all()
    return {"items": [quiz_response(row) for row in rows]}


def save_quiz(session, owner_id, document_id, revision, data, provider, content):
    document = owned_document(session, owner_id, document_id, locked=True)
    sources = document_sources(session, owner_id, document_id)
    if source_revision(sources) != revision:
        raise ApiError(
            409, "source_changed", "The document changed during generation. Generate again."
        )
    content = validate_quiz(content, sources, data)
    quiz = Quiz(
        document_id=document_id,
        title=document.title,
        source_revision=revision,
        language=data.language,
        provider=provider,
        questions=[{"id": str(uuid4()), **question} for question in content["questions"]],
    )
    session.add(quiz)
    session.commit()
    return quiz_response(quiz)


def attempt_response(attempt):
    return {
        "id": attempt.id,
        "quizId": attempt.quiz_id,
        "score": attempt.score,
        "total": attempt.total,
        "results": attempt.results,
        "createdAt": attempt.created_at.astimezone(UTC),
    }


def list_attempts(session, owner_id, quiz_id):
    owned_quiz(session, owner_id, quiz_id)
    rows = session.scalars(
        select(Attempt)
        .where(Attempt.quiz_id == quiz_id)
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .limit(100)
    ).all()
    return {"items": [attempt_response(row) for row in rows]}


def save_attempt(session, owner_id, quiz_id, data):
    quiz = owned_quiz(session, owner_id, quiz_id, locked=True)
    answers = {answer.questionId: answer.answer for answer in data.answers}
    if len(answers) != len(data.answers) or set(answers) != {q["id"] for q in quiz.questions}:
        raise ApiError(400)
    if any(answers[q["id"]] >= len(q["options"]) for q in quiz.questions):
        raise ApiError(400)
    digest = hashlib.sha256(json.dumps(answers, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(
        select(Attempt).where(Attempt.quiz_id == quiz_id, Attempt.answer_digest == digest)
    )
    if existing:
        return attempt_response(existing)
    count = session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.quiz_id == quiz_id)
    )
    if count >= 100:
        raise ApiError(
            429, "attempt_limit", "This quiz has reached its attempt limit. Create another quiz."
        )
    results = [
        {
            "questionId": question["id"],
            "answer": answers[question["id"]],
            "correctAnswer": question["correctAnswer"],
            "correct": answers[question["id"]] == question["correctAnswer"],
            "explanation": question["explanation"],
            "sourceIds": question["sourceIds"],
        }
        for question in quiz.questions
    ]
    attempt = Attempt(
        quiz_id=quiz_id,
        answer_digest=digest,
        score=sum(result["correct"] for result in results),
        total=len(results),
        results=results,
    )
    session.add(attempt)
    session.commit()
    return attempt_response(attempt)
