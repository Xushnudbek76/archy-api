from uuid import uuid4

from sqlalchemy import delete, or_, select

from app.components.academics.models import AcademicSelection, AcademicTerm, ImportBatch, Timetable
from app.components.academics.service import lock_owner
from app.components.accounts.models import AccountSession, ActionToken, SignupAttempt, User, now
from app.components.billing.service import close_allowed
from app.components.courses.models import Course
from app.components.documents.models import Document
from app.components.oauth.models import OAuthIdentity
from app.components.preferences.models import MediaPurge, NoteFormat, Profile
from app.components.processing.models import Job, Note, NotePart, Transcript, TranscriptChunk
from app.components.recordings.models import Recording, Upload
from app.components.study.models import Attempt, Quiz, QuizRetry, StudyNote
from app.components.tutor.models import Conversation, Generation, Message, Usage
from app.libs.errors import ApiError
from app.libs.security import verify_password


def close_account(session, owner_id, data):
    lock_owner(session, owner_id)
    user = session.get(User, owner_id)
    if not verify_password(data.password, user.password):
        raise ApiError(400, "invalid_password", "Check your current password.")
    close_allowed(session, owner_id)
    course_ids = list(session.scalars(select(Course.id).where(Course.owner_id == owner_id)))
    document_ids = list(session.scalars(select(Document.id).where(Document.owner_id == owner_id)))
    recording_ids = list(
        session.scalars(select(Recording.id).where(Recording.course_id.in_(course_ids)))
    )
    upload_ids = list(session.scalars(select(Upload.id).where(Upload.course_id.in_(course_ids))))
    conversations = select(Conversation.id).where(Conversation.owner_id == owner_id)
    quiz_ids = list(session.scalars(select(Quiz.id).where(Quiz.document_id.in_(document_ids))))
    attempts = select(Attempt.id).where(Attempt.quiz_id.in_(quiz_ids))
    jobs = list(
        session.scalars(select(Job.id).where(Job.recording_id.in_(recording_ids)).with_for_update())
    )
    session.execute(delete(Generation).where(Generation.conversation_id.in_(conversations)))
    session.execute(delete(Message).where(Message.conversation_id.in_(conversations)))
    session.execute(delete(Conversation).where(Conversation.owner_id == owner_id))
    session.execute(delete(Usage).where(Usage.owner_id == owner_id))
    session.execute(
        delete(QuizRetry).where(
            or_(QuizRetry.attempt_id.in_(attempts), QuizRetry.quiz_id.in_(quiz_ids))
        )
    )
    session.execute(delete(Attempt).where(Attempt.quiz_id.in_(quiz_ids)))
    session.execute(delete(Quiz).where(Quiz.id.in_(quiz_ids)))
    session.execute(delete(StudyNote).where(StudyNote.document_id.in_(document_ids)))
    session.execute(delete(Document).where(Document.owner_id == owner_id))
    for model in (Note, NotePart, Transcript, TranscriptChunk):
        session.execute(delete(model).where(model.job_id.in_(jobs)))
    session.execute(delete(Job).where(Job.id.in_(jobs)))
    session.execute(delete(Recording).where(Recording.course_id.in_(course_ids)))
    session.execute(delete(Upload).where(Upload.course_id.in_(course_ids)))
    session.execute(delete(ImportBatch).where(ImportBatch.owner_id == owner_id))
    session.execute(delete(Course).where(Course.owner_id == owner_id))
    session.execute(delete(AcademicSelection).where(AcademicSelection.owner_id == owner_id))
    session.execute(delete(Timetable).where(Timetable.owner_id == owner_id))
    session.execute(delete(AcademicTerm).where(AcademicTerm.owner_id == owner_id))
    session.execute(delete(NoteFormat).where(NoteFormat.owner_id == owner_id))
    session.execute(delete(Profile).where(Profile.owner_id == owner_id))
    session.execute(delete(OAuthIdentity).where(OAuthIdentity.owner_id == owner_id))
    session.execute(delete(ActionToken).where(ActionToken.user_id == owner_id))
    session.execute(delete(SignupAttempt).where(SignupAttempt.user_id == owner_id))
    session.execute(delete(AccountSession).where(AccountSession.user_id == owner_id))
    task = MediaPurge(
        owner_id=owner_id,
        media={
            "documents": [str(key) for key in document_ids],
            "recordings": [str(key) for key in recording_ids],
            "uploads": [str(key) for key in upload_ids],
            "jobs": [str(key) for key in jobs],
        },
    )
    session.add(task)
    user.email = f"{uuid4()}@closed.archy.invalid"
    user.display_name, user.password = "", "!closed"
    user.is_active = user.is_staff = user.is_superuser = False
    user.email_confirmed_at = None
    user.updated_at = now()
    session.commit()
    return task.id
