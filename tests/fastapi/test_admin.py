import pytest

from scripts.admin import parser, prompt_password


def test_admin_password_is_prompted(monkeypatch):
    prompts = []

    def getpass(prompt):
        prompts.append(prompt)
        return "Synthetic safe passphrase 839!"

    monkeypatch.setattr("scripts.admin.getpass", getpass)
    assert prompt_password("synthetic@example.com") == "Synthetic safe passphrase 839!"
    assert len(prompts) == 2
    with pytest.raises(SystemExit):
        parser().parse_args(["account-create", "synthetic@example.com", "--password", "exposed"])


@pytest.mark.parametrize("arguments", [["--set-password"], ["--new-email", "new@example.com"]])
def test_admin_credential_change_invalidates_reset_links(db_session, monkeypatch, arguments):
    from app.components.accounts.schemas import ResetRequest, SignupRequest
    from app.components.accounts.service import (
        confirm_email,
        request_password_reset,
        reset_password,
        signup,
    )
    from app.libs.errors import ApiError
    from scripts.admin import administer

    password = "Synthetic safe passphrase 839!"
    email = "admin-test@example.com"
    confirmation = signup(
        db_session, SignupRequest(email=email, password=password, passwordConfirmation=password)
    )
    confirm_email(db_session, confirmation.token)
    reset = request_password_reset(db_session, email)
    monkeypatch.setattr("scripts.admin.getpass", lambda prompt: "New synthetic passphrase 732!")
    administer(db_session, parser().parse_args(["account-edit", email, *arguments]))
    with pytest.raises(ApiError) as caught:
        reset_password(
            db_session,
            ResetRequest(
                uid=reset.uid, token=reset.token, password=password, passwordConfirmation=password
            ),
        )
    assert caught.value.status == 400
