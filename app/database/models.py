from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database.connection import Base

class MarketNews(Base):
    __tablename__ = "market-news"

    id = Column(String, primary_key = True, index = True)
    title = Column(String, nullable = False)
    source = Column(String, nullable = False)
    url = Column(String, unique=True , nullable=False)
    content = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SECFiling(Base):
    __tablename__ = "sec_filings"

    id = Column(String, primary_key=True, index=True)
    ticker = Column(String, index=True, nullable=True)
    form_type = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    content = Column(Text, nullable=True)
    filing_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AlphaDigest(Base):
    __tablename__ = "alpha_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_table = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    ticker_mentioned = Column(String, index = True, nullable=True)

    title = Column(String, nullable=False)
    sentiment_score = Column(Float, nullable=False)
    key_metrics = Column(Text, nullable=True)
    summary = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_in_email = Column(Boolean, default=False)
        