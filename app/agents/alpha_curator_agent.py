from pydantic import BaseModel, Field
from typing import List
from sqlalchemy.orm import Session
import os
from app.agents.base import BaseAgent
from app.database.models import AlphaDigest

class RankedItem(BaseModel):
    digest_id: int
    relevance_score: float = Field(description="1.0 to 10.0 score based on alignment with the Investor Profile.")
    curator_reasoning: str = Field(description="1 sentence explaining WHY this matters for the specific profile.")

class CuratorOutput(BaseModel):
    introduction: str = Field(description="A brief, professional pre-market intro paragraph summarizing the overall macro vibe.")
    ranked_items: List[RankedItem]

class AlphaCuratorAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.db = self.db

        profile_path = os.path.join(os.path.dirname(__file__), '..', 'profiles','investor_profile.md')
        with open(profile_path, 'r') as f:
            self.profile = f.read()

    def run(self,limit: int=10) -> CuratorOutput:
        self.logger.info("Starting Alpha Curation...")

        unsent_digests = self.db.query(AlphaDigest).filter(AlphaDigest.sent_in_email == False).all()

        if not unsent_digests:
            self.logger.info("Now new digests to curate.")
            return None
        
        payload = ""
        for d in unsent_digests:
            payload += f"ID: {d.id} | Ticker: {d.ticker_mentioned} | Title: {d.title} | Sentiment: {d.sentiment_score} | Metrics: {d.key_metrics} | Summary: {d.summary}\n\n"
        
        prompt = f"Profile:\n{self.profile}\n\nDaily Digests:\n{payload}\n\nRank the top{limit} most critical items based ONLY on alignment with Investor Profile."

        response = self.client.beta.chat.completions.parse(
            model="gpt-40",
            messages=[
                {"role": "system", "content": "You are a Chief Investment Officer curating a pre-market brief."},
                {"role": "user", "content": prompt}
            ],
            response_format = CuratorOutput,
            temperature=0.3
        )

        self.logger.info("Curation complete.")
        return response.choices[0].message.parsed