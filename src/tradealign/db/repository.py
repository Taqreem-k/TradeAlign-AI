from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from tradealign.db.models import Announcement, MarketBrief, ProcessingStatus
from tradealign.ingestion.schemas import BSEAnnouncement


class TradeAlignRepository:
    """Data access layer for BSE announcements and AI-generated market briefs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_announcements(self, items: Sequence[BSEAnnouncement]) -> int:
        """
        Bulk-insert BSE announcements while ignoring duplicates via PostgreSQL ON CONFLICT.

        Returns:
            The number of newly inserted rows.
        """
        if not items:
            return 0

        rows = [
            {
                "news_id": item.news_id,
                "scrip_code": item.scrip_code,
                "company_name": item.company_name,
                "subject": item.subject,
                "category": item.category,
                "subcategory": item.subcategory,
                "announced_at": item.announced_at,
                "attachment_name": item.attachment_name,
                "pdf_url": item.pdf_url,
                "bse_url": item.bse_url,
                "status": (
                    ProcessingStatus.PENDING
                    if item.attachment_name
                    else ProcessingStatus.SKIPPED
                ),
            }
            for item in items
        ]

        stmt = (
            pg_insert(Announcement)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["news_id"])
            .returning(Announcement.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def get_pending_announcements(self, limit: int = 20) -> list[Announcement]:
        """Fetch unprocessed announcements that have a PDF attachment, newest first."""
        stmt = (
            select(Announcement)
            .where(Announcement.status == ProcessingStatus.PENDING)
            .order_by(Announcement.announced_at.desc())
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

    async def get_unemailed_briefs(self, min_impact_score: int = 1) -> list[MarketBrief]:
        """Fetch all processed briefs that have not yet been sent in an EOD email digest."""
        stmt = (
            select(MarketBrief)
            .options(joinedload(MarketBrief.announcement))
            .where(
                MarketBrief.emailed_at.is_(None),
                MarketBrief.impact_score >= min_impact_score,
            )
            .order_by(MarketBrief.impact_score.desc(), MarketBrief.created_at.desc())
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