import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    CLAUDE_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./interview_scheduler.db")

    # Email (Gmail SMTP via App Password)
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "HR AI Assistant")

settings = Settings()
