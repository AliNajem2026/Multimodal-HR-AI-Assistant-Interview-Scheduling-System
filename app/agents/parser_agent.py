from typing import Optional
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings


class ParsedInterviewContext(BaseModel):
    candidate_name: Optional[str] = Field(None, description="The full name of the job applicant.")
    candidate_email: Optional[str] = Field(None, description="The contact email address extracted from the input text.")
    target_role: Optional[str] = Field(None, description="The position or role the candidate is applying for.")
    department: Optional[str] = Field(None, description="Categorized department. Must be exactly 'Engineering' or 'Product'.")
    is_valid: bool = Field(False, description="Set to True only if name, email, and department are successfully found.")


class InterviewParsingAgent:
    def __init__(self):
        self.llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            temperature=0.0,
            anthropic_api_key=settings.CLAUDE_API_KEY
        )
        self.structured_llm = self.llm.with_structured_output(ParsedInterviewContext)

        self.prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are an elite HR Coordination AI Agent. Analyze incoming candidate "
                    "communication data and extract structured context attributes cleanly. "
                    "Department must be mapped strictly to either 'Engineering' or 'Product' "
                    "based on the stated job role. Roles like Software Engineer, Backend, "
                    "Frontend, DevOps, Data Scientist, ML Engineer map to 'Engineering'. "
                    "Roles like Product Manager, UX Designer, Business Analyst map to 'Product'."
                ),
            ),
            ("user", "Extract structured information from this text:\n\n{raw_text}"),
        ])

        self.chain = self.prompt | self.structured_llm

    def parse_request(self, raw_text: str) -> ParsedInterviewContext:
        try:
            result = self.chain.invoke({"raw_text": raw_text})
            if result.candidate_name and result.candidate_email and result.department:
                result.is_valid = True
            return result
        except Exception:
            return ParsedInterviewContext(is_valid=False)
