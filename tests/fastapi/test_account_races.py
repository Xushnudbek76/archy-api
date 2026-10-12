from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.components.accounts.models import ActionToken, SignupAttempt, User
from app.components.accounts.schemas import ResetRequest, SignupRequest
from app.components.accounts.service import (
    confirm_email,
    request_password_reset,
    reset_password,
    signup,
)
from app.database.session import create_engine_for, session_factory
from app.libs.errors import ApiError
from app.libs.security import verify_password


@pytest.mark.parametrize("different_links", [False, True])
def test_reset_token_is_consumed_once_under_race(settings, prepared_database, different_links):
    engine = create_engine_for(settings)
    sessions = session_factory(engine)
    email = f"race-{uuid4()}@example.com"
    password = "Race safe passphrase 938!"
    user_id = None
    try:
        with sessions() as session:
            confirm = signup(
                session,
                SignupRequest(email=email, password=password, passwordConfirmation=password),
            )
            confirm_email(session, confirm.token)
            user_id = session.scalar(select(User.id).where(User.email == email))
            reset = request_password_reset(session, email)
            other = request_password_reset(session, email) if different_links else reset
        data = ResetRequest(
            uid=reset.uid,
            token=reset.token,
            password="Changed safe passphrase 726!",
            passwordConfirmation="Changed safe passphrase 726!",
        )

        def consume(link):
            with sessions() as session:
                try:
                    reset_password(
                        session, data.model_copy(update={"uid": link.uid, "token": link.token})
                    )
                    return 200
                except ApiError as error:
                    session.rollback()
                    return error.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(consume, [reset, other])) == [200, 400]
        with sessions() as session:
            user = session.get(User, user_id)
            assert verify_password(data.password, user.password)
            assert all(
                value is not None
                for value in session.scalars(
                    select(ActionToken.consumed_at).where(
                        ActionToken.digest.is_not(None),
                        ActionToken.purpose == "reset",
                        ActionToken.user_id == user_id,
                    )
                )
            )
    finally:
        if user_id:
            with sessions() as session:
                session.execute(delete(SignupAttempt).where(SignupAttempt.user_id == user_id))
                session.execute(delete(User).where(User.id == user_id))
                session.commit()
        engine.dispose()
