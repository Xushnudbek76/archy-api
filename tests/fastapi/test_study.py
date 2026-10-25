from uuid import UUID

from app.components.documents.models import Document
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_document_pdfs import new_document, upload


def test_sources_preserve_pages_and_legacy_has_no_invented_page(api_client):
    client = api_client
    signin(client)
    key = new_document(client)
    assert upload(client, key).status_code == 200
    result = client.get(f"/v1/documents/{key}/sources")
    assert result.status_code == 200
    sources = result.json()["items"]
    assert len(sources) == 1
    assert sources[0]["page"] == 1
    assert sources[0]["text"] == "Synthetic lecture text"
    assert client.get(f"/v1/documents/{key}/sources").json()["items"] == sources
    with client.app.state.sessions() as session:
        document = session.get(Document, UUID(key))
        document.pages = None
        session.commit()
    assert client.get(f"/v1/documents/{key}/sources").json()["items"][0]["page"] is None
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/documents/{key}/sources").status_code == 404


def test_sources_hide_foreign_documents(api_client):
    from app.components.accounts.models import User
    from app.libs.security import hash_password

    client = api_client
    signin(client)
    with client.app.state.sessions() as session:
        user = User(
            email="other@example.com", display_name="Other", password=hash_password("other")
        )
        session.add(user)
        session.flush()
        document = Document(owner_id=user.id, title="Other private PDF", text="Private")
        session.add(document)
        session.commit()
        key = str(document.id)
    assert client.get(f"/v1/documents/{key}/sources").status_code == 404
