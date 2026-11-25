import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
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
    """Tracks the AI analysis lifecycle of an NSE announcement."""

    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"  # No valid PDF attachment available
    FAILED = "FAILED"


class Announcement(Base):
    """Stores raw metadata for each scraped NSE corporate announcement."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="nse_api", nullable=False)
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

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
        Index(
            "ix_announcements_status_watchlist_announced_at",
            "status",
            "is_watchlist",
            "announced_at",
        ),
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