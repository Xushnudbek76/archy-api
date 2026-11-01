def register_models():
    from app.components.academics.models import (
        AcademicSelection,
        AcademicTerm,
        CourseSchedule,
        ImportBatch,
        Timetable,
    )
    from app.components.accounts.models import AccountSession, ActionToken, SignupAttempt, User
    from app.components.billing.models import BillingCustomer, BillingOrder, Subscription
    from app.components.courses.models import Course
    from app.components.documents.models import Document
    from app.components.oauth.models import OAuthIdentity, OAuthState
    from app.components.preferences.models import MediaPurge, NoteFormat, Profile
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
    from app.components.tutor.models import Conversation, Generation, Message, Usage

    return (
        BillingCustomer,
        BillingOrder,
        Subscription,
        OAuthIdentity,
        OAuthState,
        Profile,
        MediaPurge,
        NoteFormat,
        AcademicSelection,
        AcademicTerm,
        Timetable,
        CourseSchedule,
        ImportBatch,
        Conversation,
        Generation,
        Usage,
        Message,
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
