import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.database.connection import SessionLocal
from app.database.init_db import create_tables
from app.scrapers.yahoo_finance_scraper import YahooFinanceScraper
from app.scrapers.sec_edgar_scraper import SECScraper
from app.agents.sentiment_digest_agent import SentimentDigestAgent
from app.agents.alpha_curator_agent import AlphaCuratorAgent
from app.agents.premarket_email_agent import PremarketEmailAgent
from app.services.email_service import send_premarket_brief
from app.database.models import AlphaDigest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MasterRunner")
def run_pipeline():
    create_tables()
    db = SessionLocal()
    try:
        logger.info("=== STARTING ALPHA RADAR PIPELINE ===")

        logger.info("--> Phase 2: Scraping Data")
        YahooFinanceScraper(db).run()
        SECScraper(db).run()

        logger.info("--> Phase 3: AI Digestion")
        SentimentDigestAgent(db).run()

        logger.info("--> Phase 4: AI Curation")
        curator = AlphaCuratorAgent(db)
        curated_data = curator.run(limit=10)

        if curated_data and curated_data.ranked_items:
            logger.info("--> Phase 5: Email Delivery")
            html_report = PremarketEmailAgent.generate_html(curated_data)
            send_premarket_brief(html_report)

            for item in curated_data.ranked_items:
                digest = db.query(AlphaDigest).filter(AlphaDigest.id == item.digest_id).first()
                if digest:
                    digest.sent_in_email = True
            db.commit()
            logger.info("Database updated: Marked items as sent.")
        else:
            logger.info("No actionable data met the profile criteria today. Skipping email.")
        
        logger.info("=== PIPELINE COMPLETE ===")

    except Exception as e:
        logger.error(f" Pipeline crashed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_pipeline()