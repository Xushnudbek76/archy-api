import json
from pathlib import Path

from django.contrib.auth.hashers import PBKDF2PasswordHasher


def password_fixtures():
    hasher = PBKDF2PasswordHasher()
    return [
        {
            "password": password,
            "iterations": iterations,
            "encoded": hasher.encode(password, "syntheticfixture", iterations),
        }
        for password in [
            "Synthetic-safe-passphrase-827!",
            "  synthetic whitespace  ",
            "synthetic한글é",
        ]
        for iterations in [260000, 600000, hasher.iterations]
    ]


if __name__ == "__main__":
    target = Path(__file__).parents[1] / "contracts" / "pbkdf2.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(password_fixtures(), indent=2) + "\n")
