from urllib.parse import unquote

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

from app.libs.config import validate_database_url


def sqlalchemy_url(url, *, role="runtime", test=False):
    parsed, options = validate_database_url(url, role=role, test=test)
    return URL.create(
        "postgresql+psycopg",
        username=unquote(parsed.username),
        password=unquote(parsed.password),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=unquote(parsed.path[1:]),
        query=options,
    )


def create_engine_for(settings):
    return create_engine(
        sqlalchemy_url(settings.database_url, test=settings.environment == "test"),
        pool_size=5,
        max_overflow=0,
        pool_timeout=2,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c search_path=archy -c statement_timeout=5000 -c lock_timeout=5000",
        },
    )


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
