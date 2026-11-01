from pathlib import Path

from sqlalchemy import select

from app.components.accounts.models import AccountSession, User
from tests.fastapi.test_accounts import PASSWORD, post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_recordings import admit, chunk


def test_account_closure_requires_password_and_confirmation_and_removes_private_data(api_client):
    from app.components.documents.models import Document

    client = api_client
    signin(client)
    _, upload, content = admit(client)
    chunk(client, upload["id"], 0, content)
    recording = post(client, f"/v1/uploads/{upload['id']}/complete", {}).json()["recording"]
    with client.app.state.sessions() as session:
        owner = session.scalar(select(User).where(User.email == "person@example.com")).id
        docs = list(session.scalars(select(Document.id).where(Document.owner_id == owner)))
        from app.components.processing.models import Job

        job_id = session.scalar(select(Job.id).where(Job.recording_id == recording["id"]))
    root = Path(client.app.state.settings.storage_root)
    audio = root / "recordings" / f"{recording['id']}.audio"
    assert audio.is_file()
    processing = root / "processing" / f"{job_id}-00000000-0000-4000-8000-000000000000-orphan"
    processing.mkdir(parents=True)
    (processing / "decoded.flac").write_bytes(b"private decoded lecture")
    assert (
        post(
            client, "/v1/preferences/close", {"password": PASSWORD, "confirmation": "no"}
        ).status_code
        == 400
    )
    assert (
        post(
            client, "/v1/preferences/close", {"password": "wrong", "confirmation": "CLOSE"}
        ).status_code
        == 400
    )
    closed = post(client, "/v1/preferences/close", {"password": PASSWORD, "confirmation": "CLOSE"})
    assert closed.status_code == 200 and closed.json()["closed"] is True
    assert not audio.exists()
    assert not processing.exists()
    assert client.get("/v1/users/me").status_code == 403
    with client.app.state.sessions() as session:
        user = session.get(User, owner)
        assert not user.is_active and user.email.endswith("@closed.archy.invalid")
        assert (
            session.scalar(select(AccountSession.id).where(AccountSession.user_id == owner)) is None
        )
        assert not list(session.scalars(select(Document.id).where(Document.id.in_(docs))))
