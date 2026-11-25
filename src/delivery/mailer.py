import html
import logging
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

import aiosmtplib

from src.config import get_settings
from src.db.models import MarketBrief

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

SENTIMENT_COLORS = {
    "BULLISH": "#16a34a",
    "BEARISH": "#dc2626",
    "NEUTRAL": "#64748b",
}


class EmailDigestService:
    """Renders and dispatches HTML End-of-Day NSE market briefs via async SMTP."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _render_card(self, brief: MarketBrief) -> str:
        ann = brief.announcement
        color = SENTIMENT_COLORS.get(brief.sentiment.upper(), "#64748b")
        symbol = html.escape(ann.symbol)
        company = html.escape(ann.company_name)
        headline = html.escape(brief.headline)
        summary = html.escape(brief.raw_summary)
        category = html.escape(ann.category)

        watchlist_tag = (
            "<span style='background:#fef3c7;color:#b45309;font-size:11px;font-weight:700;"
            "padding:2px 7px;border-radius:999px;margin-right:6px;'>&#9733; WATCHLIST</span>"
            if ann.is_watchlist
            else ""
        )

        takeaways_li = "".join(
            f"<li style='margin-bottom:4px;'>{html.escape(point)}</li>"
            for point in brief.key_takeaways
        )

        metrics = {k: v for k, v in (brief.financial_metrics or {}).items() if v}
        metrics_html = ""
        if metrics:
            pills = " | ".join(
                f"<strong>{html.escape(k.replace('_', ' ').title())}:</strong> {html.escape(str(v))}"
                for k, v in metrics.items()
            )
            metrics_html = (
                f"<p style='font-size:13px;color:#334155;background:#f8fafc;"
                f"padding:8px 10px;border-radius:6px;margin:10px 0;'>{pills}</p>"
            )

        pdf_link = (
            f"<a href='{html.escape(ann.pdf_url)}' style='color:#2563eb;text-decoration:none;"
            f"font-size:13px;font-weight:600;'>View Official NSE PDF &rarr;</a>"
            if ann.pdf_url
            else ""
        )

        border_color = "#f59e0b" if ann.is_watchlist else "#e2e8f0"
        return f"""
        <div style="border:1px solid {border_color};border-radius:10px;padding:16px;margin-bottom:16px;background:#ffffff;">
            <div style="margin-bottom:8px;">
                {watchlist_tag}
                <span style="font-size:12px;color:#0f172a;font-weight:700;">{symbol}</span>
                <span style="font-size:12px;color:#64748b;"> &mdash; {company} &bull; {category}</span>
                <span style="float:right;background:{color};color:#ffffff;font-size:11px;font-weight:700;
                             padding:3px 8px;border-radius:999px;">
                    {html.escape(brief.sentiment)} &bull; Impact {brief.impact_score}/10
                </span>
            </div>
            <h3 style="margin:6px 0 8px 0;color:#0f172a;font-size:16px;">{headline}</h3>
            <p style="margin:0 0 10px 0;color:#334155;font-size:14px;line-height:1.5;">{summary}</p>
            {metrics_html}
            <ul style="margin:8px 0 12px 18px;padding:0;color:#1e293b;font-size:14px;line-height:1.5;">
                {takeaways_li}
            </ul>
            {pdf_link}
        </div>
        """

    def _render_html(self, briefs: Sequence[MarketBrief], report_date: str) -> str:
        watchlist_briefs = [b for b in briefs if b.announcement.is_watchlist]
        market_briefs = [b for b in briefs if not b.announcement.is_watchlist]

        sections: list[str] = []
        if watchlist_briefs:
            cards = "".join(self._render_card(b) for b in watchlist_briefs)
            sections.append(
                f"<h2 style='color:#b45309;font-size:17px;margin:20px 0 10px 0;'>"
                f"&#9733; Your Watchlist Alerts ({len(watchlist_briefs)})</h2>{cards}"
            )
        if market_briefs:
            cards = "".join(self._render_card(b) for b in market_briefs)
            sections.append(
                f"<h2 style='color:#0f172a;font-size:17px;margin:20px 0 10px 0;'>"
                f"Market-Wide High-Impact Briefs ({len(market_briefs)})</h2>{cards}"
            )

        return f"""
        <html>
          <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                       background:#f1f5f9;padding:24px;margin:0;">
            <div style="max-width:680px;margin:0 auto;">
              <h1 style="color:#0f172a;font-size:22px;margin-bottom:4px;">TradeAlign-AI Daily NSE Brief</h1>
              <p style="color:#64748b;font-size:14px;margin-top:0;margin-bottom:20px;">
                Indian Corporate Filings &bull; {report_date} (IST) &bull; {len(briefs)} filings
              </p>
              {"".join(sections)}
              <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px;">
                Generated autonomously by TradeAlign-AI. Not financial advice.
              </p>
            </div>
          </body>
        </html>
        """

    async def send_digest(self, briefs: Sequence[MarketBrief]) -> bool:
        """Send an HTML email containing all provided market briefs."""
        if not briefs:
            logger.info("No new briefs to email.")
            return False

        report_date = datetime.now(IST).strftime("%d %b %Y")
        watchlist_count = sum(1 for b in briefs if b.announcement.is_watchlist)
        subject_prefix = f"{watchlist_count} Watchlist + " if watchlist_count else ""

        message = MIMEMultipart("alternative")
        message["Subject"] = (
            f"TradeAlign-AI NSE Brief ({report_date}) — {subject_prefix}{len(briefs)} Filings"
        )
        message["From"] = self._settings.smtp_user
        message["To"] = self._settings.recipient_email

        html_body = self._render_html(briefs, report_date)
        message.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            message,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            start_tls=True,
            username=self._settings.smtp_user,
            password=self._settings.smtp_password.get_secret_value(),
        )
        logger.info(
            "Sent EOD digest with %d briefs (%d watchlist) to %s.",
            len(briefs),
            watchlist_count,
            self._settings.recipient_email,
        )
        return True