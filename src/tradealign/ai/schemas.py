import enum
from typing import Optional

from pydantic import BaseModel, Field


class Sentiment(str, enum.Enum):
    """Market sentiment classification for a corporate filing."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class FinancialMetrics(BaseModel):
    """Key financial figures extracted from the filing (if applicable)."""

    revenue: Optional[str] = Field(
        default=None,
        description="Reported revenue/turnover with currency and YoY/QoQ change (e.g., '₹1,450 Cr (+12% YoY)').",
    )
    net_profit: Optional[str] = Field(
        default=None,
        description="Net profit / PAT with currency and YoY/QoQ change (e.g., '₹210 Cr (-4% YoY)').",
    )
    ebitda_margin: Optional[str] = Field(
        default=None,
        description="EBITDA or operating margin percentage if disclosed.",
    )
    dividend_per_share: Optional[str] = Field(
        default=None,
        description="Declared dividend per share (e.g., '₹5.00 per equity share').",
    )
    deal_or_order_value: Optional[str] = Field(
        default=None,
        description="Value of any new contract, acquisition, or fundraising (e.g., '₹800 Cr').",
    )


class MarketBriefOutput(BaseModel):
    """Structured output schema bound directly to the Gemini API response."""

    headline: str = Field(
        ...,
        max_length=500,
        description="A crisp, single-sentence financial headline summarizing the core event.",
    )
    sentiment: Sentiment = Field(
        ...,
        description="Overall likely market reaction: BULLISH, BEARISH, or NEUTRAL.",
    )
    impact_score: int = Field(
        ...,
        ge=1,
        le=10,
        description=(
            "Materiality score from 1 (routine compliance/procedural filing) "
            "to 10 (major earnings beat/miss, M&A, large order win, or CEO exit)."
        ),
    )
    key_takeaways: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="3 to 5 concise, data-backed bullet points for an Indian equity investor.",
    )
    financial_metrics: FinancialMetrics = Field(
        default_factory=FinancialMetrics,
        description="Extracted headline financial numbers. Leave fields null if not in the PDF.",
    )
    raw_summary: str = Field(
        ...,
        description="A 2-3 sentence executive summary explaining why this filing matters.",
    )