from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.components.accounts.models import AccountSession, User
from app.components.accounts.schemas import LoginRequest
from app.components.accounts.service import current_identity, login, logout
from app.libs.errors import ApiError
from app.libs.security import digest_token, hash_password


def test_session_rotation_stores_only_digest(db_session):
    user = User(
        id=uuid4(),
        email="sessions@example.com",
        password=hash_password("Synthetic secure passphrase 879!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    data = LoginRequest(email=user.email, password="Synthetic secure passphrase 879!")
    first = login(db_session, data)
    second = login(db_session, data, first.token)
    rows = db_session.scalars(select(AccountSession)).all()
    assert len(rows) == 1
    assert rows[0].digest == digest_token(second.token)
    assert rows[0].digest != second.token
    assert first.token != second.token
    assert timedelta(days=6) < rows[0].expires_at - datetime.now(UTC) <= timedelta(days=7)
    with pytest.raises(ApiError):
        current_identity(db_session, first.token)
    assert current_identity(db_session, second.token).id == user.id
    logout(db_session, digest_token(second.token))
    with pytest.raises(ApiError):
        current_identity(db_session, second.token)


def test_disabled_and_expired_sessions_are_rejected(db_session):
    user = User(email="disabled@example.com", password="!unusable", is_active=False)
    db_session.add(user)
    db_session.flush()
    db_session.add(
        AccountSession(
            user_id=user.id,
            digest=digest_token("synthetic-token"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.commit()
    with pytest.raises(ApiError):
        current_identity(db_session, "synthetic-token")
