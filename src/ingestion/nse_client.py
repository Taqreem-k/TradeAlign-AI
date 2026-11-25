import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException
from pydantic import ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_settings
from src.ingestion.schemas import NSEAnnouncement

logger = logging.getLogger(__name__)

NSE_FILINGS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_API_URL = "https://www.nseindia.com/api/corporate-announcements"
NSE_RSS_URL = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"

API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_FILINGS_PAGE,
}

PDF_HEADERS = {
    "Accept": "application/pdf,*/*",
    "Referer": NSE_FILINGS_PAGE,
}

SYMBOL_PREFIX_RE = re.compile(r"^([A-Z0-9&-]{2,20})_")


class NSEClient:
    """
    Hybrid async NSE ingestion client.
    Primary: NSE Corporate Announcements JSON API (supports date ranges & rich metadata).
    Fallback: Official NSE public XML RSS feed (Online_announcements.xml).
    """

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        settings = get_settings()
        self._timeout = timeout_seconds or settings.nse_request_timeout_seconds
        self._session: Optional[AsyncSession] = None

    async def __aenter__(self) -> "NSEClient":
        self._session = AsyncSession(
            impersonate="chrome",
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("NSEClient must be used inside an 'async with' block.")
        return self._session

    async def _fetch_via_json_api(
        self,
        from_date: date,
        to_date: date,
        symbol: Optional[str] = None,
    ) -> list[NSEAnnouncement]:
        """Fetch structured announcements from NSE's JSON endpoint with lazy cookie warm-up."""
        params: dict[str, str] = {
            "index": "equities",
            "from_date": from_date.strftime("%d-%m-%Y"),
            "to_date": to_date.strftime("%d-%m-%Y"),
        }
        if symbol:
            params["symbol"] = symbol.strip().upper()

        response = await self.session.get(NSE_API_URL, params=params, headers=API_HEADERS)

        # If NSE requires session cookies, warm up via the filings page (not the homepage) and retry
        if response.status_code in (401, 403):
            logger.info("NSE API returned %d; warming up filings page cookies...", response.status_code)
            await self.session.get(NSE_FILINGS_PAGE)
            response = await self.session.get(NSE_API_URL, params=params, headers=API_HEADERS)

        response.raise_for_status()
        raw_records = response.json()
        if not isinstance(raw_records, list):
            raise ValueError(f"Unexpected NSE API response format: {type(raw_records).__name__}")

        announcements: list[NSEAnnouncement] = []
        for record in raw_records:
            try:
                seq_id = str(record.get("seq_id") or "").strip()
                pdf_url = record.get("attchmntFile") or ""
                if not seq_id:
                    seq_id = hashlib.sha256(
                        f"{record.get('symbol')}|{record.get('an_dt')}|{pdf_url}".encode()
                    ).hexdigest()[:32]

                announcements.append(
                    NSEAnnouncement(
                        filing_id=seq_id,
                        symbol=record.get("symbol") or "UNKNOWN",
                        company_name=record.get("sm_name") or record.get("symbol") or "Unknown Company",
                        category=record.get("desc") or "General",
                        subject=record.get("attchmntText") or record.get("desc") or "Corporate Announcement",
                        announced_at=record.get("an_dt") or record.get("sort_date"),
                        pdf_url=pdf_url,
                        source="nse_api",
                    )
                )
            except ValidationError as exc:
                logger.warning("Skipping malformed NSE API record: %s", exc)

        return announcements

    async def _fetch_via_rss_feed(self) -> list[NSEAnnouncement]:
        """Fallback: parse NSE's official public XML RSS feed for today's corporate announcements."""
        response = await self.session.get(NSE_RSS_URL, headers={"Accept": "application/xml, text/xml, */*"})
        response.raise_for_status()

        root = ET.fromstring(response.content)
        announcements: list[NSEAnnouncement] = []

        for item in root.findall("./channel/item"):
            company_name = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            if not company_name and not link:
                continue

            # Extract NSE ticker symbol from the PDF filename prefix (e.g., RELIANCE_23112026...pdf)
            filename = urlparse(link).path.rsplit("/", 1)[-1]
            match = SYMBOL_PREFIX_RE.match(filename.upper())
            symbol = match.group(1) if match else re.sub(r"[^A-Z0-9]", "", company_name.upper())[:12] or "NSE"

            filing_id = hashlib.sha256(f"{link}|{pub_date}|{company_name}".encode()).hexdigest()[:32]

            # RSS descriptions are often formatted as "<detail> | SUBJECT: <category>"
            category = "Corporate Announcement"
            if "|SUBJECT:" in description.upper():
                parts = re.split(r"\|SUBJECT:", description, maxsplit=1, flags=re.IGNORECASE)
                category = parts[1].strip() or category

            try:
                announcements.append(
                    NSEAnnouncement(
                        filing_id=filing_id,
                        symbol=symbol,
                        company_name=company_name or symbol,
                        category=category,
                        subject=description or company_name,
                        announced_at=pub_date,
                        pdf_url=link,
                        source="nse_rss",
                    )
                )
            except ValidationError as exc:
                logger.warning("Skipping malformed NSE RSS item: %s", exc)

        return announcements

    async def fetch_announcements(
        self,
        from_date: date,
        to_date: date,
        symbol: Optional[str] = None,
    ) -> list[NSEAnnouncement]:
        """
        Fetch NSE corporate announcements using the Primary JSON API,
        automatically falling back to NSE's official RSS feed on any error.
        """
        try:
            items = await self._fetch_via_json_api(from_date=from_date, to_date=to_date, symbol=symbol)
            if items:
                logger.info("Fetched %d announcements via NSE JSON API.", len(items))
                return items
            logger.warning("NSE JSON API returned 0 rows; checking official RSS fallback...")
        except Exception as exc:
            logger.warning("NSE JSON API failed (%s); switching to official NSE RSS fallback.", exc)

        items = await self._fetch_via_rss_feed()
        if symbol:
            target = symbol.strip().upper()
            items = [i for i in items if i.symbol == target]
        logger.info("Fetched %d announcements via NSE Official RSS feed.", len(items))
        return items

    @retry(
        retry=retry_if_exception_type(RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def download_pdf(self, pdf_url: str) -> bytes:
        """Download and verify raw PDF bytes from nsearchives.nseindia.com."""
        response = await self.session.get(pdf_url, headers=PDF_HEADERS)
        response.raise_for_status()

        if not response.content.startswith(b"%PDF"):
            raise ValueError(
                f"Downloaded payload from {pdf_url} is not a valid PDF "
                f"(Content-Type: {response.headers.get('content-type')})."
            )

        return response.content