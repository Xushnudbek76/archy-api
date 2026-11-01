from dataclasses import dataclass, field

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class BillingSettings:
    client_key: str = ""
    secret_key: str = field(default="", repr=False)
    encryption_key: str = field(default="", repr=False)
    webhook_token: str = field(default="", repr=False)

    @property
    def enabled(self):
        return bool(self.client_key and self.secret_key and self.encryption_key)


def load_billing(values):
    config = BillingSettings(
        values.get("TOSS_CLIENT_KEY", ""),
        values.get("TOSS_SECRET_KEY", ""),
        values.get("TOSS_KEY_ENCRYPTION_KEY", ""),
        values.get("TOSS_WEBHOOK_TOKEN", ""),
    )
    if any((config.client_key, config.secret_key, config.encryption_key)):
        if not config.client_key.startswith("test_ck_") or not config.secret_key.startswith(
            "test_sk_"
        ):
            raise ValueError("Only Toss test credentials are supported.")
        Fernet(config.encryption_key.encode())
    if config.webhook_token and not 32 <= len(config.webhook_token) <= 128:
        raise ValueError("Invalid webhook configuration.")
    return config
