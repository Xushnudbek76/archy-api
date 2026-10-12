import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError

from app.database.session import create_engine_for


def test_runtime_pool_is_bounded_and_sets_session_limits(settings):
    engine = create_engine_for(settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SHOW search_path")).scalar_one() == "archy"
            assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "5s"
            assert connection.execute(text("SHOW lock_timeout")).scalar_one() == "5s"
        connections = [engine.connect() for _ in range(5)]
        try:
            with pytest.raises(TimeoutError):
                engine.connect()
        finally:
            for connection in connections:
                connection.close()
    finally:
        engine.dispose()
