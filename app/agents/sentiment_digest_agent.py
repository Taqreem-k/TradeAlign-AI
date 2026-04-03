from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.agents.base import BaseAgent
from app.database.models import MarketNews, SECFiling, AlphaDigest

class DigestOutput(BaseModel):
    title: str = Field(description="A punchy, financial-focused headline.")
    ticker_mentioned: str = Field(description= "Primary stock ticker mentioned (e.g., 'AAPL'), or 'MACRO'.")
    sentiment_score: float = Field(description = "Score from 1.0 (Extremely Bearish) to 10.0 (Extremely Bullish).")
    key_metrics: str = Field(description="Comma-separated numbers (e.g., 'EPS +10%, Rev $1.2B, Margin 45%).")
    summary: str = Field(description="2-3 sentence highly dense financial summary. No fluff.")

class SentimentDigestAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.db = self.db
    
    def process_text(self, text: str) -> DigestOutput:
        prompt = f"Analyze the following financial text. Extract the core metrics and evaluate the market sentiment. \n\nText:\n{text[:15000]}"

        response = self.client.beta.chat.completions.parse(
            model="gpt-40-mini",
            messages=[
                {"role": "system", "content": "You are an elite quantitative financial analyst."},
                {"role": "user", "content": prompt}
            ],
            response_format= DigestOutput,
            temperature=0.1
        )
        return response.choices[0].message.parsed
    
    def run(self):
        self.logger.info("Starting Sentiment & Digest processing...")

        unprocessed_news = self.db.query(MarketNews).filter(
            ~MarketNews.id.in_(self.db.query(AlphaDigest.source_id))
        ).limit(10).all()

        count = 0
        for item in unprocessed_news:
            try:
                result = self.process_text(item.content or item.title)

                digest=AlphaDigest(
                    source_table = "market_news",
                    source_id = item.id,
                    ticker_mentioned=result.ticker_mentioned,
                    title=result.title,
                    sentiment_score = result.sentiment_score,
                    key_metrics = result.key_metrics,
                    summary=result.summary
                )
                self.db.add(digest)
                self.db.commit()
                count +=1
            except Exception as e:
                self.logger.error(f"Failed to process {item.id}: {e}")
        
        self.logger.info(f"Successfully generated {count} new Alpha Digests.")