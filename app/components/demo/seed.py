import hashlib
import json
import os
import secrets
import textwrap
from datetime import timedelta
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

from app.components.accounts.models import User, now
from app.components.courses.models import Course
from app.components.demo.constants import DEMO_EMAIL, DEMO_USER_ID, sample_id
from app.components.demo.content import SAMPLES
from app.components.documents.models import Document
from app.components.documents.sources import document_sources, source_revision
from app.components.documents.storage import DocumentStorage
from app.components.study.models import Attempt, Quiz, StudyNote
from app.components.tutor.models import Conversation, Message
from app.libs.security import hash_password


def sample_pdf(title, text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    lines = ["Archy sample material", title, "", *textwrap.wrap(text, 75)]
    commands = ["BT /F1 12 Tf 48 744 Td 19 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj T*")
    commands.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def save_pdf(root, document_id, body):
    with DocumentStorage(root) as storage:
        try:
            descriptor = storage.open(document_id, len(body))
        except FileNotFoundError:
            storage.publish(document_id, body)
        else:
            with os.fdopen(descriptor, "rb") as existing:
                if existing.read() != body:
                    raise ValueError("Existing sample PDF differs; inspect it before reseeding")


def seed_workspace(session, storage_root):
    user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    reserved = session.get(User, DEMO_USER_ID)
    if (user and user.id != DEMO_USER_ID) or (reserved and reserved.email != DEMO_EMAIL):
        raise ValueError("The reserved demo account conflicts with an existing account")
    if reserved and (reserved.is_staff or reserved.is_superuser):
        raise ValueError("The reserved demo account must not have administrator permissions")
    if user is None:
        session.add(
            User(
                id=DEMO_USER_ID,
                email=DEMO_EMAIL,
                display_name="Archy demo",
                password=hash_password(secrets.token_urlsafe(48)),
                is_active=True,
                email_confirmed_at=now(),
            )
        )
        session.flush()
    for sample in SAMPLES:
        course_id = sample_id(sample["key"] + ":course")
        document_id = sample_id(sample["key"] + ":document")
        if session.get(Course, course_id) is None:
            session.add(Course(id=course_id, owner_id=DEMO_USER_ID, title=sample["course"]))
            session.flush()
        elif session.get(Course, course_id).owner_id != DEMO_USER_ID:
            raise ValueError("The reserved sample course belongs to another account")
        body = sample_pdf(sample["title"], sample["text"])
        save_pdf(storage_root, document_id, body)
        document = session.get(Document, document_id)
        if document and document.owner_id != DEMO_USER_ID:
            raise ValueError("The reserved sample document belongs to another account")
        if document is None:
            session.add(
                Document(
                    id=document_id,
                    owner_id=DEMO_USER_ID,
                    course_id=course_id,
                    title=sample["title"],
                    file_name=sample["key"] + ".pdf",
                    pdf_size_bytes=len(body),
                    page_count=1,
                    text=sample["text"],
                    pages=[sample["text"]],
                )
            )
            session.flush()
        sources = document_sources(session, DEMO_USER_ID, document_id)
        revision = source_revision(sources)
        if session.get(StudyNote, document_id) is None:
            session.add(
                StudyNote(
                    document_id=document_id,
                    source_revision=revision,
                    language="en",
                    provider="demo",
                    content={
                        "overview": sample["overview"],
                        "sections": [
                            {
                                "title": "Key ideas",
                                "text": sample["text"],
                                "sourceIds": [sources[0]["id"]],
                            }
                        ],
                    },
                )
            )
        quiz_id = sample_id(sample["key"] + ":quiz")
        if session.get(Quiz, quiz_id) is None:
            session.add(
                Quiz(
                    id=quiz_id,
                    document_id=document_id,
                    title=sample["title"],
                    source_revision=revision,
                    language="en",
                    provider="demo",
                    questions=[
                        {
                            "id": str(sample_id(sample["key"] + f":question:{index}")),
                            "type": "true_false" if len(options) == 2 else "multiple_choice",
                            "prompt": prompt,
                            "options": options,
                            "correctAnswer": answer,
                            "explanation": sample["text"],
                            "sourceIds": [sources[0]["id"]],
                        }
                        for index, (prompt, options, answer) in enumerate(sample["questions"])
                    ],
                )
            )
        session.flush()
        attempt_id = sample_id(sample["key"] + ":attempt")
        if session.get(Attempt, attempt_id) is None:
            questions = session.get(Quiz, quiz_id).questions
            answers = {
                q["id"]: (q["correctAnswer"] + (index == 1)) % len(q["options"])
                for index, q in enumerate(questions)
            }
            results = [
                {
                    "questionId": q["id"],
                    "answer": answers[q["id"]],
                    "correctAnswer": q["correctAnswer"],
                    "correct": answers[q["id"]] == q["correctAnswer"],
                    "explanation": q["explanation"],
                    "sourceIds": q["sourceIds"],
                }
                for q in questions
            ]
            session.add(
                Attempt(
                    id=attempt_id,
                    quiz_id=quiz_id,
                    answer_digest=hashlib.sha256(
                        json.dumps(answers, sort_keys=True).encode()
                    ).hexdigest(),
                    score=sum(row["correct"] for row in results),
                    total=len(results),
                    results=results,
                )
            )
        conversation_id = sample_id(sample["key"] + ":conversation")
        if session.get(Conversation, conversation_id) is None:
            session.add(
                Conversation(
                    id=conversation_id,
                    owner_id=DEMO_USER_ID,
                    document_id=document_id,
                    title=sample["question"],
                )
            )
            session.flush()
            for index, (role, message) in enumerate(
                [
                    ("user", sample["question"]),
                    ("assistant", sample["answer"]),
                ]
            ):
                session.add(
                    Message(
                        id=sample_id(sample["key"] + f":message:{index}"),
                        conversation_id=conversation_id,
                        role=role,
                        text=message,
                        sources=sources if role == "assistant" else [],
                        provider="demo" if role == "assistant" else None,
                        created_at=now() + timedelta(milliseconds=index),
                    )
                )
    session.commit()
    return {"userId": str(DEMO_USER_ID), "courses": len(SAMPLES), "documents": len(SAMPLES)}
