from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from src.db.models import Announcement, MarketBrief, ProcessingStatus
from src.ingestion.schemas import NSEAnnouncement


class TradeAlignRepository:
    """Data access layer for NSE announcements and AI-generated market briefs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_announcements(
        self,
        items: Sequence[NSEAnnouncement],
        watchlist: Optional[set[str]] = None,
    ) -> int:
        """
        Bulk-insert NSE announcements while ignoring duplicates via PostgreSQL ON CONFLICT.

        Returns:
            The number of newly inserted rows.
        """
        if not items:
            return 0

        watchlist_symbols = watchlist or set()
        rows = [
            {
                "filing_id": item.filing_id,
                "symbol": item.symbol,
                "company_name": item.company_name,
                "category": item.category,
                "subject": item.subject,
                "announced_at": item.announced_at,
                "pdf_url": item.pdf_url,
                "source": item.source,
                "is_watchlist": item.symbol in watchlist_symbols,
                "status": (
                    ProcessingStatus.PENDING
                    if item.pdf_url
                    else ProcessingStatus.SKIPPED
                ),
            }
            for item in items
        ]

        stmt = (
            pg_insert(Announcement)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["filing_id"])
            .returning(Announcement.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def get_pending_announcements(self, limit: int = 10) -> list[Announcement]:
        """
        Fetch unprocessed announcements with PDFs.
        Prioritizes Watchlist stocks first, then newest market-wide filings.
        """
        stmt = (
            select(Announcement)
            .where(Announcement.status == ProcessingStatus.PENDING)
            .order_by(Announcement.is_watchlist.desc(), Announcement.announced_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_market_brief(
        self,
        announcement_id: int,
        headline: str,
        sentiment: str,
        impact_score: int,
        key_takeaways: list[str],
        financial_metrics: dict,
        raw_summary: str,
    ) -> MarketBrief:
        """Persist an AI-generated brief and mark its parent announcement as PROCESSED."""
        brief = MarketBrief(
            announcement_id=announcement_id,
            headline=headline,
            sentiment=sentiment,
            impact_score=impact_score,
            key_takeaways=key_takeaways,
            financial_metrics=financial_metrics,
            raw_summary=raw_summary,
        )
        self.session.add(brief)

        await self.session.execute(
            update(Announcement)
            .where(Announcement.id == announcement_id)
            .values(status=ProcessingStatus.PROCESSED, error_message=None)
        )
        return brief

    async def mark_announcement_failed(self, announcement_id: int, error: str) -> None:
        """Record a processing failure so the pipeline does not loop infinitely on bad PDFs."""
        await self.session.execute(
            update(Announcement)
            .where(Announcement.id == announcement_id)
            .values(status=ProcessingStatus.FAILED, error_message=error[:1000])
        )

    async def get_unemailed_briefs(self, min_impact_score: int = 6) -> list[MarketBrief]:
        """
        Fetch all unemailed briefs that either belong to the user's Watchlist
        OR meet the high-impact market threshold.
        """
        stmt = (
            select(MarketBrief)
            .join(MarketBrief.announcement)
            .options(contains_eager(MarketBrief.announcement))
            .where(
                MarketBrief.emailed_at.is_(None),
                or_(
                    Announcement.is_watchlist.is_(True),
                    MarketBrief.impact_score >= min_impact_score,
                ),
            )
            .order_by(
                Announcement.is_watchlist.desc(),
                MarketBrief.impact_score.desc(),
                MarketBrief.created_at.desc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_briefs_emailed(self, brief_ids: Sequence[int]) -> None:
        """Stamp briefs with the current UTC timestamp after a successful email send."""
        if not brief_ids:
            return
        await self.session.execute(
            update(MarketBrief)
            .where(MarketBrief.id.in_(brief_ids))
            .values(emailed_at=datetime.now(timezone.utc))
        )