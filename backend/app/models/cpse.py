from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Cpse(Base):
    __tablename__ = "cpses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    short_code = Column(String(20), unique=True, nullable=False)
    sap_url = Column(String(500), nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    users = relationship("User", back_populates="cpse")
