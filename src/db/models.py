import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


class ProcessingStatus(str, enum.Enum):
    """Tracks the AI analysis lifecycle of a BSE announcement."""

    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"  # No PDF attachment available
    FAILED = "FAILED"


class Announcement(Base):
    """Stores raw metadata for each scraped BSE corporate announcement."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    scrip_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attachment_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bse_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brief: Mapped[Optional["MarketBrief"]] = relationship(
        back_populates="announcement",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_announcements_status_announced_at", "status", "announced_at"),
    )


class MarketBrief(Base):
    """Stores the structured Gemini AI financial brief for an announcement."""

    __tablename__ = "market_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    impact_score: Mapped[int] = mapped_column(Integer, nullable=False)
    key_takeaways: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    financial_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_summary: Mapped[str] = mapped_column(Text, nullable=False)

    emailed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    announcement: Mapped["Announcement"] = relationship(back_populates="brief")