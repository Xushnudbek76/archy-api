import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from dotenv import dotenv_values

from app.libs.config import validate_database_url


def postgres_environment(url, *, role="migration", test=False):
    parsed, options = validate_database_url(url, role=role, test=test)
    values = dict(os.environ)
    # Ignore unrelated shell defaults when selecting the database.
    for key in list(values):
        if key.startswith("PG"):
            values.pop(key)
    values.update(
        PGHOST=parsed.hostname,
        PGPORT=str(parsed.port or 5432),
        PGUSER=unquote(parsed.username),
        PGPASSWORD=unquote(parsed.password),
        PGDATABASE=unquote(parsed.path[1:]),
        PGCONNECT_TIMEOUT="5",
        PGAPPNAME="archy-snapshot",
        PGSSLMODE=options.get("sslmode", "disable"),
    )
    if "sslrootcert" in options:
        values["PGSSLROOTCERT"] = options["sslrootcert"]
    return values


def postgres_tool(name, pg_bin=None):
    path = Path(pg_bin) / name if pg_bin else shutil.which(name)
    if not path or not Path(path).is_file():
        raise ValueError("PostgreSQL client tools are required")
    return str(path)


def snapshot_database(url, directory, pg_bin=None):
    environment = postgres_environment(url)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / f"{uuid4()}.dump"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    try:
        subprocess.run(
            [
                postgres_tool("pg_dump", pg_bin),
                "--format=custom",
                "--schema=archy",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(path),
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Take a private consistent Archy schema snapshot with migration credentials."
    )
    parser.add_argument("--env", default=".env.migrations")
    parser.add_argument("--directory", default=".local/backups")
    parser.add_argument("--pg-bin")
    args = parser.parse_args()
    try:
        path = snapshot_database(
            dotenv_values(args.env).get("DATABASE_URL", ""), args.directory, args.pg_bin
        )
    except Exception:
        print(
            "Snapshot failed; check private configuration and PostgreSQL client tools.",
            file=sys.stderr,
        )
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
