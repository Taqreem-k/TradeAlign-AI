from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

IST = timezone(timedelta(hours=5, minutes=30))


def parse_nse_datetime(value: object) -> datetime:
    """Parse NSE timestamps (IST string or RFC-2822 RSS date) into timezone-aware datetimes."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)

    if isinstance(value, str):
        cleaned = value.strip()
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%d-%b-%Y",
        ):
            try:
                return datetime.strptime(cleaned, fmt).replace(tzinfo=IST)
            except ValueError:
                continue

        try:
            dt = parsedate_to_datetime(cleaned)
            return dt if dt.tzinfo else dt.replace(tzinfo=IST)
        except (TypeError, ValueError):
            pass

    return datetime.now(IST)


class NSEAnnouncement(BaseModel):
    """Unified validated schema for an NSE Corporate Announcement (JSON API or RSS)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    filing_id: str = Field(..., description="Unique filing identifier for deduplication.")
    symbol: str = Field(..., description="NSE equity ticker symbol (e.g., RELIANCE, TCS).")
    company_name: str = Field(..., description="Full registered company name.")
    category: str = Field(default="General", description="NSE announcement category/type.")
    subject: str = Field(..., description="Announcement headline or summary text.")
    announced_at: datetime = Field(..., description="Broadcast timestamp in IST.")
    pdf_url: Optional[str] = Field(default=None, description="Direct URL to the official NSE PDF.")
    source: str = Field(default="nse_api", description="Ingestion source: 'nse_api' or 'nse_rss'.")

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, v: object) -> str:
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
        return "UNKNOWN"

    @field_validator("company_name", "category", "subject", mode="before")
    @classmethod
    def strip_text(cls, v: object) -> str:
        if isinstance(v, str) and v.strip():
            return v.strip()
        return "General"

    @field_validator("announced_at", mode="before")
    @classmethod
    def coerce_announced_at(cls, v: object) -> datetime:
        return parse_nse_datetime(v)

    @field_validator("pdf_url", mode="before")
    @classmethod
    def validate_pdf_url(cls, v: object) -> Optional[str]:
        """Keep only valid HTTP(S) PDF attachment links; ignore .xml/.zip placeholders."""
        if not isinstance(v, str):
            return None
        cleaned = v.strip()
        if cleaned.startswith(("http://", "https://")) and cleaned.lower().endswith(".pdf"):
            return cleaned
        return None