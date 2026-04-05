from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from google.genai import types
from app.agents.base import BaseAgent
from app.database.models import MarketNews, SECFiling, AlphaDigest

class DigestOutput(BaseModel):
    source_id: str = Field(description="The exact ID of the article provided in the prompt.")
    title: str = Field(description="A punchy, financial-focused headline.")
    ticker_mentioned: str = Field(description="Primary stock ticker mentioned (e.g., 'AAPL'), or 'MACRO'.")
    sentiment_score: float = Field(description="Score from 1.0 (Extremely Bearish) to 10.0 (Extremely Bullish).")
    key_metrics: str = Field(description="Comma-separated numbers (e.g., 'EPS +12%, Rev $1.2B, Margin 45%').")
    summary: str = Field(description="2-3 sentence highly dense financial summary. No fluff.")

class BatchDigestOutput(BaseModel):
    digests: list[DigestOutput]

class SentimentDigestAgent(BaseAgent):
    def __init__(self, db: Session):
        super().__init__()
        self.db = db

    def run(self):
        self.logger.info("Starting Sentiment & Digest processing with Gemini Batching...")
        
        unprocessed_news = self.db.query(MarketNews).filter(
            ~MarketNews.id.in_(self.db.query(AlphaDigest.source_id))
        ).limit(10).all()

        if not unprocessed_news:
            self.logger.info("No new articles to process.")
            return

        payload = ""
        for item in unprocessed_news:
            # We truncate to 5000 chars per article just to keep it incredibly fast
            content_snippet = (item.content or item.title)[:5000]
            payload += f"--- ARTICLE ID: {item.id} ---\n{content_snippet}\n\n"

        prompt = f"Analyze the following financial articles. Extract the core metrics and evaluate the market sentiment for EACH article separately. Map them back using the ARTICLE ID.\n\n{payload}"

        try:
            self.logger.info(f"Sending 1 batched API call for {len(unprocessed_news)} articles...")
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    "You are an elite quantitative financial analyst. Process these articles in a single batch.",
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BatchDigestOutput,
                    temperature=0.1
                ),
            )

            batch_result = BatchDigestOutput.model_validate_json(response.text)

            count = 0
            for result in batch_result.digests:
                digest = AlphaDigest(
                    source_table="market_news",
                    source_id=result.source_id, # Safely maps the AI output back to the correct DB row
                    ticker_mentioned=result.ticker_mentioned,
                    title=result.title,
                    sentiment_score=result.sentiment_score,
                    key_metrics=result.key_metrics,
                    summary=result.summary
                )
                self.db.add(digest)
                count += 1
            
            self.db.commit()
            self.logger.info(f"Successfully generated {count} new Alpha Digests in a single API call.")
            
        except Exception as e:
            self.logger.error(f"Failed to process batch: {e}")