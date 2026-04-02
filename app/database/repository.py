from sqlalchemy.orm import Session
from app.database.models import MarketNews, SECFiling
import logging

def save_market_news(db: Session, news_data: dict) -> bool:
    if not db.query(MarketNews).filter(MarketNews.id == news_data['id']).first():
        news = MarketNews(**news_data)
        db.add(news)
        db.commit()
        return True
    return False

def save_sec_filing(db: Session, filing_data: dict)-> bool:
    if not db.query(SECFiling).filter(SECFiling.id == filing_data['id']).first():
        filing = SECFiling(**filing_data)
        db.add(filing)
        db.commit()
        return True
    return False