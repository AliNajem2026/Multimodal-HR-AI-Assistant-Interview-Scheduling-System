from sqlalchemy import Column, Integer, String
from app.database.connection import Base

class CandidateRecord(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    target_role = Column(String, nullable=True)
    department = Column(String, nullable=True)
    status = Column(String, default="In Progress - Scheduling")
    assigned_panel = Column(String, nullable=True)
    confirmed_slot = Column(String, nullable=True)
    calendar_event_id = Column(String, nullable=True)
