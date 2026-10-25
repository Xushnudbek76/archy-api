from uuid import UUID

from app.components.documents.models import Document
from tests.fastapi.test_accounts import post
from tests.fastapi.test_study import notes_document


def conversation(client):
    document_id = notes_document(client)
    response = post(client, f"/v1/documents/{document_id}/conversations", {})
    assert response.status_code == 201
    return document_id, response.json()


def test_tutor_conversations_persist_private_history(api_client):
    client = api_client
    document_id, created = conversation(client)
    assert created["documentId"] == document_id
    assert created["title"] and created["createdAt"]
    assert client.get(f"/v1/documents/{document_id}/conversations").json() == {"items": [created]}
    assert client.get(f"/v1/conversations/{created['id']}").json() == {**created, "messages": []}
    assert (
        post(
            client, f"/v1/documents/{document_id}/conversations", {"ownerId": "forged"}
        ).status_code
        == 400
    )
    assert post(client, f"/v1/documents/{document_id}/archive", {}).status_code == 200
    assert client.get(f"/v1/conversations/{created['id']}").status_code == 404
    assert client.get(f"/v1/documents/{document_id}/conversations").status_code == 404
    assert post(client, f"/v1/documents/{document_id}/conversations", {}).status_code == 404


def test_tutor_conversation_is_private_after_document_transfer(api_client):
    from app.components.accounts.models import User
    from app.libs.security import hash_password

    client = api_client
    document_id, created = conversation(client)
    with client.app.state.sessions() as session:
        other = User(email="private-tutor@example.com", password=hash_password("synthetic"))
        session.add(other)
        session.flush()
        session.get(Document, UUID(document_id)).owner_id = other.id
        session.commit()
    assert client.get(f"/v1/conversations/{created['id']}").status_code == 404
    assert post(client, f"/v1/documents/{document_id}/conversations", {}).status_code == 404
