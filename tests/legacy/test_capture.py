import json

from tests.legacy.generate_password_fixtures import password_fixtures


def test_legacy_fixtures_verify_synthetic_passwords():
    from django.contrib.auth.hashers import check_password

    fixtures = password_fixtures()
    assert {item["iterations"] for item in fixtures} == {260000, 600000, 1000000}
    for item in fixtures:
        assert check_password(item["password"], item["encoded"])
        assert not check_password("wrong synthetic password", item["encoded"])
    assert "DATABASE_URL" not in json.dumps(fixtures)


def test_baseline_contains_health_routes_and_all_account_workflows():
    from pathlib import Path

    records = json.loads((Path(__file__).parents[1] / "contracts/legacy-api.json").read_text())
    paths = {record["path"] for record in records}
    assert {
        "/v1/health/live",
        "/v1/health/ready",
        "/v1/auth/signup",
        "/v1/auth/confirm-email",
        "/v1/auth/password-reset",
        "/v1/auth/password-reset/confirm",
        "/v1/uploads/{id}/cancel",
    } <= paths


def test_capture_redacts_private_configuration():
    import os
    from pathlib import Path

    data = (Path(__file__).parents[1] / "contracts/legacy-api.json").read_text()
    assert os.environ.get("DATABASE_URL", "not-present") not in data
    assert "Synthetic-safe-passphrase-827!" not in data
    assert "@example.com" not in data
