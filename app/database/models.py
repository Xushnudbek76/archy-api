def register_models():
    from app.components.accounts.models import AccountSession, ActionToken, SignupAttempt, User
    from app.components.courses.models import Course
    from app.components.documents.models import Document
    from app.components.processing.models import (
        Job,
        Note,
        NotePart,
        ProviderGate,
        Transcript,
        TranscriptChunk,
    )
    from app.components.recordings.models import Recording, Upload
    from app.components.study.models import Attempt, Quiz, QuizRetry, StudyNote

    return (
        StudyNote,
        Quiz,
        Attempt,
        QuizRetry,
        User,
        SignupAttempt,
        AccountSession,
        ActionToken,
        Course,
        Document,
        Upload,
        Recording,
        Job,
        TranscriptChunk,
        Transcript,
        NotePart,
        Note,
        ProviderGate,
    )
