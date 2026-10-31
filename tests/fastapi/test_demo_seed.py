from sqlalchemy import func, select

from app.components.accounts.models import User
from app.components.documents.models import Document
from app.components.documents.sources import document_sources, source_revision
from app.components.study.models import Quiz, StudyNote


def test_seed_is_repeatable_and_keeps_other_accounts(db_session, settings):
    from app.components.demo.constants import DEMO_USER_ID
    from app.components.demo.seed import seed_workspace

    other = User(email="other-demo-test@example.com", password="unusable")
    db_session.add(other)
    db_session.commit()
    first = seed_workspace(db_session, settings.storage_root)
    second = seed_workspace(db_session, settings.storage_root)
    assert first == second
    assert db_session.get(User, other.id).email == other.email
    assert (
        db_session.scalar(
            select(func.count()).select_from(Document).where(Document.owner_id == DEMO_USER_ID)
        )
        == 2
    )
    for document in db_session.scalars(select(Document).where(Document.owner_id == DEMO_USER_ID)):
        sources = document_sources(db_session, document.owner_id, document.id)
        assert sources and sources[0]["page"] == 1
        assert db_session.get(StudyNote, document.id).source_revision == source_revision(sources)
        quiz = db_session.scalar(select(Quiz).where(Quiz.document_id == document.id))
        assert len(quiz.questions) == 5 and quiz.provider == "demo"
        from io import BytesIO

        from pypdf import PdfReader

        path = settings.storage_root / "documents" / f"{document.id}.pdf"
        assert "HTTP" in PdfReader(BytesIO(path.read_bytes())).pages[0].extract_text() or (
            "transaction" in PdfReader(BytesIO(path.read_bytes())).pages[0].extract_text()
        )


def test_seed_refuses_reserved_account_collision(db_session, settings):
    import pytest

    from app.components.demo.constants import DEMO_EMAIL
    from app.components.demo.seed import seed_workspace

    db_session.add(User(email=DEMO_EMAIL, password="unusable"))
    db_session.commit()
    with pytest.raises(ValueError, match="reserved"):
        seed_workspace(db_session, settings.storage_root)
