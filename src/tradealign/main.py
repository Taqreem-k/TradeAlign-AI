import asyncio
import logging
import signal
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from tradealign.ai.analyzer import GeminiAnalyzer
from tradealign.config import get_settings
from tradealign.db.models import Announcement
from tradealign.db.repository import TradeAlignRepository
from tradealign.db.session import get_db_session, init_db
from tradealign.delivery.mailer import EmailDigestService
from tradealign.ingestion.bse_client import BSEClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("tradealign.worker")

IST = ZoneInfo("Asia/Kolkata")
MAX_CONCURRENT_ANALYSES = 3
BATCH_SIZE = 10
MIN_DIGEST_IMPACT_SCORE = 6


async def _process_single_announcement(
    semaphore: asyncio.Semaphore,
    bse_client: BSEClient,
    analyzer: GeminiAnalyzer,
    announcement: Announcement,
) -> None:
    """Download PDF, run Gemini analysis, and persist the result for one filing."""
    async with semaphore:
        try:
            if not announcement.attachment_name:
                return

            pdf_bytes = await bse_client.download_pdf(announcement.attachment_name)
            brief_output = await analyzer.analyze_filing(
                company_name=announcement.company_name,
                subject=announcement.subject,
                category=announcement.category,
                pdf_bytes=pdf_bytes,
            )

            async with get_db_session() as session:
                repo = TradeAlignRepository(session)
                await repo.save_market_brief(
                    announcement_id=announcement.id,
                    headline=brief_output.headline,
                    sentiment=brief_output.sentiment.value,
                    impact_score=brief_output.impact_score,
                    key_takeaways=brief_output.key_takeaways,
                    financial_metrics=brief_output.financial_metrics.model_dump(exclude_none=True),
                    raw_summary=brief_output.raw_summary,
                )

            logger.info(
                "Processed [%s] %s (Impact: %d/10, Sentiment: %s)",
                announcement.scrip_code,
                announcement.company_name,
                brief_output.impact_score,
                brief_output.sentiment.value,
            )
        except Exception as exc:
            logger.exception("Failed processing announcement id=%d: %s", announcement.id, exc)
            async with get_db_session() as session:
                repo = TradeAlignRepository(session)
                await repo.mark_announcement_failed(announcement.id, str(exc))


async def run_ingestion_and_analysis() -> None:
    """Scheduled job: scrape today's BSE announcements and analyze pending PDFs."""
    today_ist = datetime.now(IST).date()
    logger.info("Starting BSE ingestion cycle for %s...", today_ist)

    analyzer = GeminiAnalyzer()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)

    async with BSEClient() as bse_client:
        announcements = await bse_client.fetch_announcements(
            from_date=today_ist,
            to_date=today_ist,
        )

        async with get_db_session() as session:
            repo = TradeAlignRepository(session)
            inserted_count = await repo.upsert_announcements(announcements)
            pending = await repo.get_pending_announcements(limit=BATCH_SIZE)

        logger.info(
            "Fetched %d announcements (%d new). Processing %d pending filings.",
            len(announcements),
            inserted_count,
            len(pending),
        )

        if pending:
            tasks = [
                _process_single_announcement(semaphore, bse_client, analyzer, ann)
                for ann in pending
            ]
            await asyncio.gather(*tasks)


async def run_eod_digest() -> None:
    """Scheduled job: compile and email all unemailed high-impact briefs."""
    logger.info("Running EOD email digest job...")
    mailer = EmailDigestService()

    async with get_db_session() as session:
        repo = TradeAlignRepository(session)
        briefs = await repo.get_unemailed_briefs(min_impact_score=MIN_DIGEST_IMPACT_SCORE)
        if not briefs:
            logger.info("No high-impact briefs queued for EOD digest.")
            return

        sent = await mailer.send_digest(briefs)
        if sent:
            await repo.mark_briefs_emailed([b.id for b in briefs])


async def main() -> None:
    settings = get_settings()
    await init_db()
    logger.info("Database initialized.")

    scheduler = AsyncIOScheduler(timezone=IST)

    # Poll BSE every N minutes during Indian market & post-market hours (Mon-Fri, 09:00-17:00 IST)
    scheduler.add_job(
        run_ingestion_and_analysis,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-17",
            minute=f"*/{settings.bse_poll_interval_minutes}",
            timezone=IST,
        ),
        id="bse_ingestion_job",
        max_instances=1,
        coalesce=True,
    )

    # Dispatch End-of-Day HTML Digest at 5:15 PM IST (Mon-Fri)
    scheduler.add_job(
        run_eod_digest,
        trigger=CronTrigger(day_of_week="mon-fri", hour=17, minute=15, timezone=IST),
        id="eod_digest_job",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("TradeAlign-AI scheduler started (IST timezone).")

    # Run one immediate ingestion cycle on boot for instant feedback
    await run_ingestion_and_analysis()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows ProactorEventLoop does not support add_signal_handler
            pass

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        logger.info("TradeAlign-AI worker shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())