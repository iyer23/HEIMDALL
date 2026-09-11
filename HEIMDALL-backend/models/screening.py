from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from database.db import Base
import json

class ScreeningRecord(Base):
    __tablename__ = "screenings"

    screening_id     = Column(String, primary_key=True, index=True)
    timestamp        = Column(DateTime(timezone=True), server_default=func.now())
    document_type    = Column(String, nullable=False)
    doc_type_conf    = Column(Float, default=0.0)
    nationality      = Column(String, nullable=True)
    risk_score       = Column(Integer, default=0)
    decision         = Column(String, nullable=False)
    processing_time  = Column(Integer, default=0)   # ms
    demo_mode        = Column(Boolean, default=False)
    full_result_json = Column(Text, nullable=True)  # full JSON blob

    def set_result(self, data: dict):
        self.full_result_json = json.dumps(data)

    def get_result(self) -> dict | None:
        if self.full_result_json:
            return json.loads(self.full_result_json)
        return None
