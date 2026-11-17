
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True
    )
    file_type: Mapped[str] = mapped_column(String(20))

    language: Mapped[str] = mapped_column(String(10), default="en")

    # public, student, staff, admin
    visibility: Mapped[str] = mapped_column(
        String(30),
        default="public"
    )

    # pending, processing, completed, failed
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending"
    )

    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )

    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    # 384 dimensions for multilingual-e5-small
    embedding = mapped_column(Vector(384), nullable=True)

    document: Mapped["Document"] = relationship(
        back_populates="chunks"
    )
