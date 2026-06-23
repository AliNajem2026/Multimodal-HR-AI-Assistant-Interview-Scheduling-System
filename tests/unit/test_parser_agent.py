from unittest.mock import MagicMock, patch
import pytest
from app.agents.parser_agent import InterviewParsingAgent, ParsedInterviewContext


def _make_agent() -> InterviewParsingAgent:
    """Instantiate InterviewParsingAgent without triggering the real LLM constructor."""
    agent = object.__new__(InterviewParsingAgent)
    agent.chain = MagicMock()
    return agent


class TestParseRequest:
    def test_valid_extraction_marks_context_as_valid(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(
            candidate_name="Jane Doe",
            candidate_email="jane@example.com",
            target_role="Backend Engineer",
            department="Engineering",
            is_valid=False,  # parse_request sets this to True if fields present
        )

        result = agent.parse_request("Hi, I'm Jane Doe...")

        assert result.is_valid is True
        assert result.candidate_name == "Jane Doe"
        assert result.candidate_email == "jane@example.com"
        assert result.department == "Engineering"

    def test_missing_email_returns_invalid(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(
            candidate_name="Jane Doe",
            candidate_email=None,
            department="Engineering",
            is_valid=False,
        )

        result = agent.parse_request("Just a name, no email.")

        assert result.is_valid is False

    def test_missing_department_returns_invalid(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(
            candidate_name="Jane Doe",
            candidate_email="jane@example.com",
            department=None,
            is_valid=False,
        )

        result = agent.parse_request("Name and email but no role.")

        assert result.is_valid is False

    def test_missing_name_returns_invalid(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(
            candidate_name=None,
            candidate_email="jane@example.com",
            department="Engineering",
            is_valid=False,
        )

        result = agent.parse_request("email@example.com for Backend role.")

        assert result.is_valid is False

    def test_chain_exception_returns_safe_fallback(self):
        agent = _make_agent()
        agent.chain.invoke.side_effect = RuntimeError("LLM API unreachable")

        result = agent.parse_request("any text")

        assert result.is_valid is False
        assert result.candidate_name is None
        assert result.candidate_email is None

    def test_chain_invoke_receives_raw_text(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(is_valid=False)

        agent.parse_request("my custom raw text")

        agent.chain.invoke.assert_called_once_with({"raw_text": "my custom raw text"})

    def test_product_department_is_preserved(self):
        agent = _make_agent()
        agent.chain.invoke.return_value = ParsedInterviewContext(
            candidate_name="Bob Smith",
            candidate_email="bob@example.com",
            target_role="Product Manager",
            department="Product",
            is_valid=False,
        )

        result = agent.parse_request("Bob Smith, PM role, bob@example.com")

        assert result.is_valid is True
        assert result.department == "Product"
