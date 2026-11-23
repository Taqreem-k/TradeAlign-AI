from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


BSE_ATTACH_LIVE_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
BSE_ATTACH_HIS_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"


class BSEAnnouncement(BaseModel):

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    news_id: str = Field(alias="NEWSID", description="Unique BSE announcement UUID.")
    scrip_code: int = Field(alias="SCRIP_CD", description="6-digit BSE company code.")
    company_name: str = Field(alias="SLONGNAME", description="Full registered company name.")
    subject: str = Field(alias="NEWSSUB", description="Announcement headline/subject.")
    category: str = Field(alias="CATEGORYNAME", default="General")
    subcategory: Optional[str] = Field(alias="SUBCATNAME", default=None)
    announced_at: datetime = Field(alias="NEWS_DT", description="Timestamp of filing.")
    attachment_name: Optional[str] = Field(alias="ATTACHMENTNAME", default=None)
    bse_url: Optional[str] = Field(alias="NSURL", default=None)

    @field_validator("company_name", "subject", "category", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("attachment_name", "subcategory", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: object) -> Optional[str]:
        if isinstance(v, str) and not v.strip():
            return None
        return v if isinstance(v, str) else None

    @computed_field
    @property
    def pdf_url(self) -> Optional[str]:
        """Constructs the primary live PDF URL if an attachment exists."""
        if not self.attachment_name:
            return None
        return f"{BSE_ATTACH_LIVE_BASE}{self.attachment_name}"