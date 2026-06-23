import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Must be set before any app import so config.py reads them at class-definition time
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-ci")
os.environ.setdefault("EMAIL_ENABLED", "false")

from app.main import app
from app.database.connection import Base, get_db
from app.agents.parser_agent import ParsedInterviewContext

# Single shared in-memory SQLite DB for the whole test session.
# StaticPool ensures all sessions share the same connection so tables created
# by create_all() are visible to every session derived from this engine.
_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_TEST_ENGINE)
_TestSession = sessionmaker(bind=_TEST_ENGINE, autocommit=False, autoflush=False)


@pytest.fixture()
def db_session():
    """Yields a SQLAlchemy session connected to the in-memory test DB.
    Deletes all candidate rows after each test to keep tests independent."""
    session = _TestSession()
    try:
        yield session
    finally:
        from app.database.models import CandidateRecord
        session.query(CandidateRecord).delete()
        session.commit()
        session.close()


@pytest.fixture()
def api_client(db_session):
    """FastAPI TestClient with get_db overridden to use the test session."""
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def make_valid_context(**overrides) -> ParsedInterviewContext:
    """Factory for ParsedInterviewContext with sensible test defaults."""
    defaults = dict(
        candidate_name="Jane Doe",
        candidate_email="jane@example.com",
        target_role="Senior Backend Engineer",
        department="Engineering",
        is_valid=True,
    )
    defaults.update(overrides)
    return ParsedInterviewContext(**defaults)
