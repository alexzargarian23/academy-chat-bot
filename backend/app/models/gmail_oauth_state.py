
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"

    id: Mapped[int] = mapped_column(primary_key=True)

    state: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )

    code_verifier: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
        + timedelta(minutes=10),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
