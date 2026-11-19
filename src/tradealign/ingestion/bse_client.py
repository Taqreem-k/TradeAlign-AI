import logging
from datetime import date
from typing import Optional

import httpx
from pydantic import ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tradealign.config import get_settings
from tradealign.ingestion.schemas import (
    BSE_ATTACH_HIS_BASE,
    BSE_ATTACH_LIVE_BASE,
    BSEAnnouncement,
)

logger = logging.getLogger(__name__)

BSE_ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}


class BSEClient:
    """Async HTTP client for scraping BSE corporate announcements and PDF filings."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        settings = get_settings()
        self._timeout = timeout_seconds or settings.bse_request_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BSEClient":
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("BSEClient must be used inside an 'async with' block.")
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_announcements(
        self,
        from_date: date,
        to_date: date,
        category: str = "-1",
        scrip_code: str = "",
        page: int = 1,
    ) -> list[BSEAnnouncement]:
        """
        Fetch corporate announcements from BSE for a given date range.

        Args:
            from_date: Start date (inclusive).
            to_date: End date (inclusive).
            category: BSE category filter (e.g., 'Result', 'Board Meeting', or '-1' for all).
            scrip_code: Optional 6-digit BSE scrip code (e.g., '500325' for Reliance).
            page: Pagination index (1-based).
        """
        params = {
            "pageno": page,
            "strCat": category,
            "strPrevDate": from_date.strftime("%Y%m%d"),
            "strToDate": to_date.strftime("%Y%m%d"),
            "strSc_code": scrip_code,
            "strSearch": "P",
            "strType": "C",
            "subcategory": "-1",
        }

        response = await self.client.get(BSE_ANNOUNCEMENTS_URL, params=params)
        response.raise_for_status()
        payload = response.json()

        raw_records = payload.get("Table") or []
        announcements: list[BSEAnnouncement] = []

        for record in raw_records:
            try:
                announcements.append(BSEAnnouncement.model_validate(record))
            except ValidationError as exc:
                logger.warning(
                    "Skipping malformed BSE record (NEWSID=%s): %s",
                    record.get("NEWSID"),
                    exc,
                )

        return announcements

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def download_pdf(self, attachment_name: str) -> bytes:
        """
        Download raw PDF bytes for a BSE announcement.
        Tries the live folder first, falling back to the historical archive folder on 404.
        """
        live_url = f"{BSE_ATTACH_LIVE_BASE}{attachment_name}"
        response = await self.client.get(live_url)

        if response.status_code == 404:
            logger.info("PDF not found in AttachLive, trying AttachHis: %s", attachment_name)
            his_url = f"{BSE_ATTACH_HIS_BASE}{attachment_name}"
            response = await self.client.get(his_url)

        response.raise_for_status()

        if not response.content.startswith(b"%PDF"):
            raise ValueError(
                f"Downloaded payload for {attachment_name} is not a valid PDF "
                f"(Content-Type: {response.headers.get('content-type')})."
            )

        return response.content