from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderCredentials:
    client_id: str = ""
    client_secret: str = field(default="", repr=False)

    @property
    def enabled(self):
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class OAuthSettings:
    google: ProviderCredentials = field(default_factory=ProviderCredentials)
    kakao: ProviderCredentials = field(default_factory=ProviderCredentials)
    apple: ProviderCredentials = field(default_factory=ProviderCredentials)


def load_oauth(values):
    return OAuthSettings(
        **{
            name: ProviderCredentials(
                values.get(f"{name.upper()}_CLIENT_ID", ""),
                values.get(f"{name.upper()}_CLIENT_SECRET", ""),
            )
            for name in ("google", "kakao", "apple")
        }
    )
