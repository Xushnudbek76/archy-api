import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from uuid import uuid4

from sqlalchemy import delete, select, text

from app.components.academics.service import lock_owner
from app.components.accounts.models import User
from app.components.documents.models import Document
from app.components.documents.service import owned_document
from app.components.tutor.models import Conversation
from app.components.tutor.service import owned_conversation
from app.database.session import create_engine_for, session_factory


def test_owner_locked_closure_can_acquire_conversation_during_a_tutor_finish(
    settings, prepared_database
):
    engine = create_engine_for(settings)
    sessions = session_factory(engine)
    owner, document, conversation = uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(
            User(
                id=owner,
                email=f"locking-{owner}@example.com",
                password="!synthetic",
                is_active=True,
            )
        )
        session.flush()
        session.add(Document(id=document, owner_id=owner, title="Lecture"))
        session.flush()
        session.add(
            Conversation(id=conversation, owner_id=owner, document_id=document, title="Lecture")
        )
    identifiers = Queue()

    def finish():
        with sessions() as session:
            identifiers.put(session.scalar(text("SELECT pg_backend_pid()")))
            owned_conversation(session, owner, conversation, locked=True)
            owned_document(session, owner, document, locked=True)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with sessions() as closure:
                lock_owner(closure, owner)
                task = executor.submit(finish)
                pid = identifiers.get(timeout=2)
                try:
                    deadline = time.monotonic() + 3
                    while (
                        closure.scalar(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": pid},
                        )
                        != "Lock"
                    ):
                        if time.monotonic() > deadline:
                            raise AssertionError("Tutor did not reach its owner lock")
                        time.sleep(0.02)
                        closure.execute(text("SELECT pg_stat_clear_snapshot()"))
                    assert (
                        closure.scalar(
                            select(Conversation)
                            .where(Conversation.id == conversation)
                            .with_for_update(nowait=True)
                        )
                        is not None
                    )
                finally:
                    closure.rollback()
            task.result(timeout=3)
    finally:
        with sessions.begin() as session:
            session.execute(delete(Conversation).where(Conversation.id == conversation))
            session.execute(delete(Document).where(Document.id == document))
            session.execute(delete(User).where(User.id == owner))
        engine.dispose()
