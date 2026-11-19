from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ChannelIdentity(Base):
    __tablename__ = "channel_identities"
    __table_args__ = (UniqueConstraint("provider", "external_user_id", name="uq_channel_identity_provider_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False, default="Guest")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pending_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_auth_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
    conversation = relationship("Conversation")
