import sys
from uuid import UUID

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.database.session import sqlalchemy_url


def main():
    identifier = UUID(sys.argv[1])
    url = dotenv_values(".env.test")["TEST_MIGRATION_URL"]
    engine = create_engine(
        sqlalchemy_url(url, role="migration", test=True), poolclass=NullPool, hide_parameters=True
    )
    try:
        with engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "UPDATE archy.recordings_upload SET max_duration_seconds=NULL WHERE id=:id "
                        "AND status='UPLOADING'"
                    ),
                    {"id": identifier},
                ).rowcount
                == 1
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
