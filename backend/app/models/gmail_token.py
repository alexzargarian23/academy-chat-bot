
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GmailToken(Base):
    __tablename__ = "gmail_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
