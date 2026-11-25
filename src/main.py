import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from google.genai import errors as genai_errors

from src.ai.analyzer import GeminiAnalyzer
from src.config import get_settings
from src.db.models import Announcement
from src.db.repository import TradeAlignRepository
from src.db.session import get_db_session, init_db
from src.delivery.mailer import EmailDigestService
from src.ingestion.nse_client import NSEClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("tradealign.worker")

try:
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

BATCH_SIZE = 5
GEMINI_PACE_SECONDS = 13.0  # Keeps throughput <= 4.6 RPM (safely under Free Tier 5 RPM cap)
MIN_DIGEST_IMPACT_SCORE = 6


async def _process_single_announcement(
    nse_client: NSEClient,
    analyzer: GeminiAnalyzer,
    announcement: Announcement,
) -> bool:
    """
    Download PDF, run Gemini analysis, and persist the result for one filing.
    Returns False if a 429 quota limit was hit (signaling the batch to pause).
    """
    try:
        if not announcement.pdf_url:
            return True

        pdf_bytes = await nse_client.download_pdf(announcement.pdf_url)
        brief_output = await analyzer.analyze_filing(
            symbol=announcement.symbol,
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

        tag = "[WATCHLIST] " if announcement.is_watchlist else ""
        logger.info(
            "Processed %s[%s] %s (Impact: %d/10, Sentiment: %s)",
            tag,
            announcement.symbol,
            announcement.company_name,
            brief_output.impact_score,
            brief_output.sentiment.value,
        )
        return True

    except genai_errors.APIError as exc:
        if exc.code in (429, 503):
            logger.warning(
                "Gemini 429 quota hit on [%s]; leaving status as PENDING for next cycle.",
                announcement.symbol,
            )
            return False
        logger.exception("Gemini API error on announcement id=%d: %s", announcement.id, exc)
        async with get_db_session() as session:
            repo = TradeAlignRepository(session)
            await repo.mark_announcement_failed(announcement.id, str(exc))
        return True

    except Exception as exc:
        logger.exception("Failed processing announcement id=%d: %s", announcement.id, exc)
        async with get_db_session() as session:
            repo = TradeAlignRepository(session)
            await repo.mark_announcement_failed(announcement.id, str(exc))
        return True


async def run_ingestion_and_analysis() -> None:
    """Scheduled job: scrape recent NSE announcements and analyze prioritized PDFs."""
    settings = get_settings()
    today_ist = datetime.now(IST).date()
    from_date = today_ist - timedelta(days=1)
    watchlist = settings.watchlist_set

    logger.info(
        "Starting NSE ingestion cycle (%s to %s) | Watchlist: %d stocks...",
        from_date,
        today_ist,
        len(watchlist),
    )

    analyzer = GeminiAnalyzer()

    async with NSEClient() as nse_client:
        announcements = await nse_client.fetch_announcements(
            from_date=from_date,
            to_date=today_ist,
        )

        async with get_db_session() as session:
            repo = TradeAlignRepository(session)
            inserted_count = await repo.upsert_announcements(announcements, watchlist=watchlist)
            pending = await repo.get_pending_announcements(limit=BATCH_SIZE)

        watchlist_pending = sum(1 for a in pending if a.is_watchlist)
        logger.info(
            "Fetched %d NSE filings (%d new). Processing %d pending (%d watchlist).",
            len(announcements),
            inserted_count,
            len(pending),
            watchlist_pending,
        )

        for idx, ann in enumerate(pending):
            ok = await _process_single_announcement(nse_client, analyzer, ann)
            if not ok:
                logger.warning("Stopping batch early due to Gemini rate limit.")
                break
            if idx < len(pending) - 1:
                await asyncio.sleep(GEMINI_PACE_SECONDS)


async def run_eod_digest() -> None:
    """Scheduled job: compile and email all unemailed Watchlist & high-impact briefs."""
    logger.info("Running EOD email digest job...")
    mailer = EmailDigestService()

    async with get_db_session() as session:
        repo = TradeAlignRepository(session)
        briefs = await repo.get_unemailed_briefs(min_impact_score=MIN_DIGEST_IMPACT_SCORE)
        if not briefs:
            logger.info("No Watchlist or high-impact briefs queued for EOD digest.")
            return

        sent = await mailer.send_digest(briefs)
        if sent:
            await repo.mark_briefs_emailed([b.id for b in briefs])


async def main() -> None:
    settings = get_settings()
    await init_db()
    logger.info("Database initialized.")

    scheduler = AsyncIOScheduler(timezone=IST)

    scheduler.add_job(
        run_ingestion_and_analysis,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-17",
            minute=f"*/{settings.nse_poll_interval_minutes}",
            timezone=IST,
        ),
        id="nse_ingestion_job",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        run_eod_digest,
        trigger=CronTrigger(day_of_week="mon-fri", hour=17, minute=15, timezone=IST),
        id="eod_digest_job",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("TradeAlign-AI scheduler started (IST timezone).")

    try:
        await run_ingestion_and_analysis()
    except Exception as exc:
        logger.exception("Initial ingestion cycle failed (scheduler remains active): %s", exc)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
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